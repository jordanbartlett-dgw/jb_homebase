from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic import ValidationError

from jordan_claw.gateway.models import GatewayResponse

BODY = {"text": "log my workout", "agent_slug": "workout", "idempotency_key": "utt-1"}

# Stored user-message row the replay path returns from the messages table.
USER_ROW = {
    "id": "m1",
    "conversation_id": "c1",
    "role": "user",
    "content": "log my workout",
    "created_at": "2026-07-05T10:00:00+00:00",
    "metadata": {"agent_slug": "workout"},
}
ASSISTANT_ROW = {
    "content": "Logged it.",
    "created_at": "2026-07-05T10:00:33+00:00",
}


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


# --- AppMessageRequest ---


def test_request_strips_idempotency_key_and_rejects_blank():
    from jordan_claw.gateway.app_chat import AppMessageRequest

    req = AppMessageRequest(text="hi", agent_slug="claw-main", idempotency_key="  utt-1  ")
    assert req.idempotency_key == "utt-1"

    with pytest.raises(ValidationError, match="must not be blank"):
        AppMessageRequest(text="hi", agent_slug="claw-main", idempotency_key="   ")


def test_request_rejects_empty_text():
    from jordan_claw.gateway.app_chat import AppMessageRequest

    with pytest.raises(ValidationError):
        AppMessageRequest(text="", agent_slug="claw-main", idempotency_key="utt-1")


# --- channel_message_id ---


def test_channel_message_id_composes_channel_slug_and_key():
    from jordan_claw.gateway.app_chat import channel_message_id

    assert channel_message_id("workout", "utt-1") == "app-workout-utt-1"
    # Distinct agents never collide on the same client key
    assert channel_message_id("claw-main", "utt-1") == "app-claw-main-utt-1"


def test_channel_message_id_strips_and_caps_key():
    from jordan_claw.gateway.app_chat import channel_message_id

    assert channel_message_id("workout", "  utt-1  ") == "app-workout-utt-1"
    assert channel_message_id("workout", "k" * 300) == "app-workout-" + "k" * 120


# --- replay_app_response ---


async def test_replay_returns_original_reply_with_metadata_slug():
    from jordan_claw.gateway import voice
    from jordan_claw.gateway.app_chat import replay_app_response

    db = MagicMock()
    with patch.object(
        voice, "get_assistant_reply_after", new=AsyncMock(return_value=ASSISTANT_ROW)
    ):
        result = await replay_app_response(db, USER_ROW, fallback_slug="claw-main")

    assert result.agent_slug == "workout"
    assert result.reply == "Logged it."
    assert result.conversation_id == "c1"


async def test_replay_falls_back_to_request_slug_when_metadata_missing():
    from jordan_claw.gateway import voice
    from jordan_claw.gateway.app_chat import replay_app_response

    row = {**USER_ROW, "metadata": None}
    db = MagicMock()
    with patch.object(
        voice, "get_assistant_reply_after", new=AsyncMock(return_value=ASSISTANT_ROW)
    ):
        result = await replay_app_response(db, row, fallback_slug="claw-main")

    assert result.agent_slug == "claw-main"
    assert result.reply == "Logged it."


# --- handle_app_message channel overrides (generalized for text) ---


async def test_handle_app_message_accepts_channel_thread_and_run_kind_overrides(monkeypatch):
    from jordan_claw.analytics.types import RunKind
    from jordan_claw.gateway.voice import handle_app_message

    gateway_response = GatewayResponse(content="Logged.", conversation_id="c1")
    mock_handle = AsyncMock(return_value=gateway_response)
    monkeypatch.setattr("jordan_claw.gateway.voice.handle_message", mock_handle)

    db = MagicMock()
    result = await handle_app_message(
        db,
        org_id="org-1",
        agent_slug="workout",
        text="log my workout",
        settings=_settings(),
        channel_message_id="app-workout-utt-1",
        channel="app",
        channel_thread_id="workout",
        run_kind=RunKind.USER_MESSAGE,
    )

    assert result is gateway_response
    msg = mock_handle.call_args.args[0]
    assert msg.channel == "app"
    assert msg.channel_thread_id == "workout"
    assert msg.channel_message_id == "app-workout-utt-1"
    assert mock_handle.call_args.kwargs["run_kind"] == RunKind.USER_MESSAGE


# --- /app/messages route ---


def _client() -> httpx.AsyncClient:
    from jordan_claw.main import app

    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _wire_app_state(app_token: str) -> MagicMock:
    from jordan_claw.main import app

    settings = _settings(app_token)
    app.state.settings = settings
    app.state.db = MagicMock()
    return settings


async def test_app_messages_returns_503_when_token_unconfigured():
    _wire_app_state(app_token="")
    async with _client() as client:
        resp = await client.post(
            "/app/messages", json=BODY, headers={"Authorization": "Bearer anything"}
        )
    assert resp.status_code == 503


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param({}, id="missing-auth"),
        pytest.param({"Authorization": "Bearer wrong-token"}, id="wrong-token"),
        pytest.param({"Authorization": "Basic app-token"}, id="wrong-scheme"),
    ],
)
async def test_app_messages_returns_401_on_bad_auth(headers):
    _wire_app_state(app_token="app-token")
    async with _client() as client:
        resp = await client.post("/app/messages", json=BODY, headers=headers)
    assert resp.status_code == 401


async def test_app_messages_returns_422_on_blank_text():
    _wire_app_state(app_token="app-token")
    async with _client() as client:
        resp = await client.post(
            "/app/messages",
            json={**BODY, "text": ""},
            headers={"Authorization": "Bearer app-token"},
        )
    assert resp.status_code == 422


async def test_app_messages_happy_path_runs_gateway_and_returns_reply():
    from jordan_claw import main
    from jordan_claw.analytics.types import RunKind

    _wire_app_state(app_token="app-token")
    gateway_response = GatewayResponse(content="Logged it.", conversation_id="c1")

    with (
        patch.object(main, "get_message_by_channel_id", new=AsyncMock(return_value=None)),
        patch.object(
            main, "handle_app_message", new=AsyncMock(return_value=gateway_response)
        ) as mock_handle,
    ):
        async with _client() as client:
            resp = await client.post(
                "/app/messages", json=BODY, headers={"Authorization": "Bearer app-token"}
            )

    assert resp.status_code == 200
    assert resp.json() == {
        "agent_slug": "workout",
        "reply": "Logged it.",
        "conversation_id": "c1",
    }
    kwargs = mock_handle.call_args.kwargs
    assert kwargs["org_id"] == "org-1"
    assert kwargs["agent_slug"] == "workout"
    assert kwargs["text"] == "log my workout"
    assert kwargs["channel_message_id"] == "app-workout-utt-1"
    assert kwargs["channel"] == "app"
    # One gateway conversation per agent, matching the app's thread-per-agent UI
    assert kwargs["channel_thread_id"] == "workout"
    assert kwargs["run_kind"] == RunKind.USER_MESSAGE


async def test_app_messages_replay_converges_without_rerunning_agent():
    from jordan_claw import main
    from jordan_claw.gateway import voice

    _wire_app_state(app_token="app-token")

    with (
        patch.object(main, "get_message_by_channel_id", new=AsyncMock(return_value=USER_ROW)),
        patch.object(voice, "get_assistant_reply_after", new=AsyncMock(return_value=ASSISTANT_ROW)),
        patch.object(main, "handle_app_message", new=AsyncMock()) as mock_handle,
    ):
        async with _client() as client:
            resp = await client.post(
                "/app/messages", json=BODY, headers={"Authorization": "Bearer app-token"}
            )

    assert resp.status_code == 200
    assert resp.json() == {
        "agent_slug": "workout",
        "reply": "Logged it.",
        "conversation_id": "c1",
    }
    mock_handle.assert_not_called()


async def test_app_messages_replay_times_out_with_504(monkeypatch):
    from jordan_claw import main
    from jordan_claw.gateway import voice

    _wire_app_state(app_token="app-token")
    monkeypatch.setattr(voice, "POLL_TIMEOUT_S", 0.05)
    monkeypatch.setattr(voice, "POLL_INTERVAL_S", 0.01)

    with (
        patch.object(main, "get_message_by_channel_id", new=AsyncMock(return_value=USER_ROW)),
        patch.object(voice, "get_assistant_reply_after", new=AsyncMock(return_value=None)),
    ):
        async with _client() as client:
            resp = await client.post(
                "/app/messages", json=BODY, headers={"Authorization": "Bearer app-token"}
            )

    assert resp.status_code == 504
