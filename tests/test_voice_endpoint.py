from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from jordan_claw.gateway.models import GatewayResponse

AUDIO = b"\x00\x01fake-m4a-bytes"


def _settings(app_token: str = "app-token") -> MagicMock:
    settings = MagicMock()
    settings.claw_app_token = app_token
    settings.default_org_id = "org-1"
    settings.openai_api_key = "oa-key"
    settings.tavily_api_key = "tv"
    settings.fastmail_username = "u"
    settings.fastmail_app_password = "p"
    settings.message_history_limit = 50
    settings.environment = "development"
    return settings


# --- transcribe ---


def _install_fake_httpx(monkeypatch, *, status_code=200, json_body=None, exc=None) -> dict:
    """Replace httpx.AsyncClient in the voice module. Returns a call recorder."""
    recorder: dict = {}

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            recorder["client_kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, **kwargs):
            if exc is not None:
                raise exc
            recorder["url"] = url
            recorder.update(kwargs)
            response = MagicMock()
            response.status_code = status_code
            response.text = "whisper says no"
            response.json.return_value = json_body if json_body is not None else {}
            return response

    monkeypatch.setattr("jordan_claw.gateway.voice.httpx.AsyncClient", FakeAsyncClient)
    return recorder


async def test_transcribe_posts_multipart_and_returns_text(monkeypatch):
    from jordan_claw.gateway.voice import transcribe

    recorder = _install_fake_httpx(monkeypatch, json_body={"text": "log my workout"})

    text = await transcribe(AUDIO, "note.m4a", "audio/m4a", _settings())

    assert text == "log my workout"
    assert recorder["url"] == "https://api.openai.com/v1/audio/transcriptions"
    assert recorder["headers"]["Authorization"] == "Bearer oa-key"
    assert recorder["data"] == {"model": "whisper-1"}
    assert recorder["files"]["file"] == ("note.m4a", AUDIO, "audio/m4a")
    assert recorder["client_kwargs"]["timeout"] == 60.0


async def test_transcribe_raises_on_non_200(monkeypatch):
    from jordan_claw.gateway.voice import TranscriptionError, transcribe

    _install_fake_httpx(monkeypatch, status_code=500)

    with pytest.raises(TranscriptionError, match=r"Transcription failed \(HTTP 500\)") as excinfo:
        await transcribe(AUDIO, "note.m4a", "audio/m4a", _settings())

    # Provider response body is logged server-side, never returned to the client
    assert "whisper says no" not in str(excinfo.value)


async def test_transcribe_raises_on_network_error(monkeypatch):
    from jordan_claw.gateway.voice import TranscriptionError, transcribe

    _install_fake_httpx(monkeypatch, exc=httpx.ConnectError("no route"))

    with pytest.raises(TranscriptionError):
        await transcribe(AUDIO, "note.m4a", "audio/m4a", _settings())


# --- handle_app_message ---


async def test_handle_app_message_runs_gateway_flow_as_voice(monkeypatch):
    from jordan_claw.analytics.types import RunKind
    from jordan_claw.gateway.voice import handle_app_message

    gateway_response = GatewayResponse(content="Logged.", conversation_id="c1")
    mock_handle = AsyncMock(return_value=gateway_response)
    monkeypatch.setattr("jordan_claw.gateway.voice.handle_message", mock_handle)

    db = MagicMock()
    result = await handle_app_message(
        db,
        org_id="org-1",
        agent_slug="workout-coach",
        text="log my workout",
        settings=_settings(),
    )

    assert result is gateway_response
    msg = mock_handle.call_args.args[0]
    assert msg.channel == "app-voice"
    assert msg.channel_thread_id == "app-voice"
    assert msg.content == "log my workout"
    assert msg.org_id == "org-1"
    kwargs = mock_handle.call_args.kwargs
    assert kwargs["db"] is db
    assert kwargs["agent_slug"] == "workout-coach"
    assert kwargs["run_kind"] is RunKind.VOICE
    assert kwargs.get("bot") is None


# --- /voice route ---


def _voice_client() -> httpx.AsyncClient:
    from jordan_claw.main import app

    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _wire_app_state(app_token: str) -> MagicMock:
    from jordan_claw.main import app

    settings = _settings(app_token)
    app.state.settings = settings
    app.state.db = MagicMock()
    app.state.bots = {}
    return settings


async def test_voice_returns_503_when_token_unconfigured():
    _wire_app_state(app_token="")
    async with _voice_client() as client:
        resp = await client.post(
            "/voice", content=AUDIO, headers={"Authorization": "Bearer anything"}
        )
    assert resp.status_code == 503


async def test_voice_returns_401_on_missing_auth():
    _wire_app_state(app_token="app-token")
    async with _voice_client() as client:
        resp = await client.post("/voice", content=AUDIO)
    assert resp.status_code == 401


async def test_voice_returns_401_on_wrong_token():
    _wire_app_state(app_token="app-token")
    async with _voice_client() as client:
        resp = await client.post(
            "/voice", content=AUDIO, headers={"Authorization": "Bearer wrong-token"}
        )
    assert resp.status_code == 401


async def test_voice_happy_path_returns_transcript_slug_and_reply():
    from jordan_claw import main

    _wire_app_state(app_token="app-token")
    gateway_response = GatewayResponse(content="Logged it.", conversation_id="c1")

    with (
        patch.object(
            main, "transcribe", new=AsyncMock(return_value="log my workout")
        ) as mock_transcribe,
        patch.object(main, "classify", new=AsyncMock(return_value="workout-coach")) as mock_cls,
        patch.object(
            main, "handle_app_message", new=AsyncMock(return_value=gateway_response)
        ) as mock_handle,
    ):
        async with _voice_client() as client:
            resp = await client.post(
                "/voice",
                content=AUDIO,
                headers={
                    "Authorization": "Bearer app-token",
                    "Content-Type": "audio/m4a",
                    "X-Audio-Filename": "note.m4a",
                },
            )

    assert resp.status_code == 200
    assert resp.json() == {
        "transcript": "log my workout",
        "agent_slug": "workout-coach",
        "reply": "Logged it.",
    }
    audio_arg, filename_arg, content_type_arg = mock_transcribe.call_args.args[:3]
    assert audio_arg == AUDIO
    assert filename_arg == "note.m4a"
    assert content_type_arg == "audio/m4a"
    assert mock_cls.call_args.args[1] == "log my workout"
    assert mock_cls.call_args.args[2] == "org-1"
    handle_kwargs = mock_handle.call_args.kwargs
    assert handle_kwargs["org_id"] == "org-1"
    assert handle_kwargs["agent_slug"] == "workout-coach"
    assert handle_kwargs["text"] == "log my workout"


async def test_voice_returns_502_on_transcription_failure():
    from jordan_claw import main
    from jordan_claw.gateway.voice import TranscriptionError

    _wire_app_state(app_token="app-token")

    with patch.object(
        main,
        "transcribe",
        new=AsyncMock(side_effect=TranscriptionError("Transcription failed (HTTP 500)")),
    ):
        async with _voice_client() as client:
            resp = await client.post(
                "/voice", content=AUDIO, headers={"Authorization": "Bearer app-token"}
            )

    assert resp.status_code == 502
    assert resp.json()["detail"] == "Transcription failed (HTTP 500)"
