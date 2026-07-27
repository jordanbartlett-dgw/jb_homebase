from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic import ValidationError

VALID_TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"

BODY = {
    "traceparent": VALID_TRACEPARENT,
    "name": "helpful",
    "value": True,
}


def _settings(app_token: str = "app-token", logfire_token: str | None = "lf-token") -> MagicMock:
    settings = MagicMock()
    settings.claw_app_token = app_token
    settings.logfire_token = logfire_token
    return settings


# --- FeedbackRequest ---


def test_request_rejects_malformed_traceparent():
    from jordan_claw.gateway.app_feedback import FeedbackRequest

    with pytest.raises(ValidationError):
        FeedbackRequest(traceparent="not-a-traceparent", name="helpful", value=True)


def test_request_rejects_bad_name():
    from jordan_claw.gateway.app_feedback import FeedbackRequest

    with pytest.raises(ValidationError):
        FeedbackRequest(traceparent=VALID_TRACEPARENT, name="Not Valid!", value=True)


def test_request_rejects_long_string_value():
    from jordan_claw.gateway.app_feedback import FeedbackRequest

    with pytest.raises(ValidationError):
        FeedbackRequest(traceparent=VALID_TRACEPARENT, name="note", value="x" * 201)


def test_request_rejects_long_comment():
    from jordan_claw.gateway.app_feedback import FeedbackRequest

    with pytest.raises(ValidationError):
        FeedbackRequest(
            traceparent=VALID_TRACEPARENT, name="helpful", value=True, comment="x" * 2001
        )


def test_request_bool_value_stays_bool():
    from jordan_claw.gateway.app_feedback import FeedbackRequest

    req = FeedbackRequest(traceparent=VALID_TRACEPARENT, name="helpful", value=True)
    assert req.value is True
    assert isinstance(req.value, bool)


def test_request_int_value_stays_int_not_bool():
    from jordan_claw.gateway.app_feedback import FeedbackRequest

    req = FeedbackRequest(traceparent=VALID_TRACEPARENT, name="rating", value=1)
    assert req.value == 1
    assert isinstance(req.value, int)
    assert not isinstance(req.value, bool)


def test_request_float_value_stays_float():
    from jordan_claw.gateway.app_feedback import FeedbackRequest

    req = FeedbackRequest(traceparent=VALID_TRACEPARENT, name="rating", value=4.5)
    assert req.value == 4.5
    assert isinstance(req.value, float)


def test_request_string_value_stays_string():
    from jordan_claw.gateway.app_feedback import FeedbackRequest

    req = FeedbackRequest(traceparent=VALID_TRACEPARENT, name="note", value="great")
    assert req.value == "great"


def test_request_comment_defaults_to_none():
    from jordan_claw.gateway.app_feedback import FeedbackRequest

    req = FeedbackRequest(traceparent=VALID_TRACEPARENT, name="helpful", value=True)
    assert req.comment is None


# --- record_app_feedback ---


async def test_record_app_feedback_calls_record_feedback_with_exact_args():
    from jordan_claw.gateway import app_feedback

    body = app_feedback.FeedbackRequest(
        traceparent=VALID_TRACEPARENT, name="helpful", value=True, comment="nice"
    )
    with patch.object(app_feedback, "record_feedback") as mock_record:
        await app_feedback.record_app_feedback(_settings(), body)

    mock_record.assert_called_once_with(VALID_TRACEPARENT, "helpful", True, comment="nice")
    # Bool must not have been coerced to an int (0/1) on the way through.
    assert mock_record.call_args.args[2] is True


async def test_record_app_feedback_wraps_failures():
    from jordan_claw.gateway import app_feedback

    body = app_feedback.FeedbackRequest(traceparent=VALID_TRACEPARENT, name="helpful", value=True)
    with (
        patch.object(app_feedback, "record_feedback", side_effect=RuntimeError("boom")),
        pytest.raises(app_feedback.FeedbackRecordError),
    ):
        await app_feedback.record_app_feedback(_settings(), body)


# --- POST /app/feedback route ---


def _client() -> httpx.AsyncClient:
    from jordan_claw.main import app

    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _wire_app_state(
    app_token: str = "app-token", logfire_token: str | None = "lf-token"
) -> MagicMock:
    from jordan_claw.main import app

    settings = _settings(app_token=app_token, logfire_token=logfire_token)
    app.state.settings = settings
    app.state.db = MagicMock()
    return settings


async def test_feedback_returns_503_when_app_token_unconfigured():
    _wire_app_state(app_token="")
    async with _client() as client:
        resp = await client.post(
            "/app/feedback", json=BODY, headers={"Authorization": "Bearer anything"}
        )
    assert resp.status_code == 503


async def test_feedback_returns_503_when_logfire_token_unconfigured():
    _wire_app_state(app_token="app-token", logfire_token=None)
    async with _client() as client:
        resp = await client.post(
            "/app/feedback", json=BODY, headers={"Authorization": "Bearer app-token"}
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
async def test_feedback_returns_401_on_bad_auth(headers):
    _wire_app_state()
    async with _client() as client:
        resp = await client.post("/app/feedback", json=BODY, headers=headers)
    assert resp.status_code == 401


async def test_feedback_returns_422_on_malformed_traceparent():
    _wire_app_state()
    async with _client() as client:
        resp = await client.post(
            "/app/feedback",
            json={**BODY, "traceparent": "bogus"},
            headers={"Authorization": "Bearer app-token"},
        )
    assert resp.status_code == 422


async def test_feedback_returns_422_on_bad_name():
    _wire_app_state()
    async with _client() as client:
        resp = await client.post(
            "/app/feedback",
            json={**BODY, "name": "Not Valid"},
            headers={"Authorization": "Bearer app-token"},
        )
    assert resp.status_code == 422


async def test_feedback_happy_path_returns_202_and_dispatches():
    from jordan_claw import main

    _wire_app_state()
    with patch.object(main, "record_app_feedback", new=AsyncMock(return_value=None)) as mock_record:
        async with _client() as client:
            resp = await client.post(
                "/app/feedback", json=BODY, headers={"Authorization": "Bearer app-token"}
            )

    assert resp.status_code == 202
    assert resp.json() == {"status": "recorded"}
    mock_record.assert_awaited_once()
    body_arg = mock_record.call_args.args[1]
    assert body_arg.value is True
    assert isinstance(body_arg.value, bool)


async def test_feedback_returns_502_when_record_fails():
    from jordan_claw import main
    from jordan_claw.gateway.app_feedback import FeedbackRecordError

    _wire_app_state()
    with patch.object(
        main, "record_app_feedback", new=AsyncMock(side_effect=FeedbackRecordError("boom"))
    ):
        async with _client() as client:
            resp = await client.post(
                "/app/feedback", json=BODY, headers={"Authorization": "Bearer app-token"}
            )

    assert resp.status_code == 502
