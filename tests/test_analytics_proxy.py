from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from jordan_claw.analytics.types import RunKind
from jordan_claw.gateway.analytics_proxy import build_analytics_router

ORG_ID = "00000000-0000-0000-0000-000000000001"
TOKEN = "test-frontend-token"


def _app_with_token(token: str | None = TOKEN) -> FastAPI:
    app = FastAPI()
    app.include_router(build_analytics_router(token=token, org_id=ORG_ID))
    return app


def test_missing_token_returns_401():
    client = TestClient(_app_with_token())
    resp = client.post(
        "/api/analytics/event",
        json={"event": "agent_session_started", "distinct_id": "u-1", "properties": {}},
    )
    assert resp.status_code == 401


def test_bad_token_returns_401():
    client = TestClient(_app_with_token())
    resp = client.post(
        "/api/analytics/event",
        json={"event": "agent_session_started", "distinct_id": "u-1", "properties": {}},
        headers={"Authorization": "Bearer wrong"},
    )
    assert resp.status_code == 401


def test_unknown_event_returns_400():
    client = TestClient(_app_with_token())
    resp = client.post(
        "/api/analytics/event",
        json={"event": "definitely_not_a_real_event", "distinct_id": "u-1", "properties": {}},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert resp.status_code == 400


def test_valid_request_returns_202_and_dispatches_to_emitter():
    with patch(
        "jordan_claw.gateway.analytics_proxy.emitter.agent_session_started",
        new=AsyncMock(),
    ) as mock_emit:
        client = TestClient(_app_with_token())
        resp = client.post(
            "/api/analytics/event",
            json={
                "event": "agent_session_started",
                "distinct_id": "user-42",
                "properties": {"channel": "web", "agent_slug": "claw-main"},
            },
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

    assert resp.status_code == 202
    mock_emit.assert_awaited_once()
    kwargs = mock_emit.call_args.kwargs
    # org_id is server-resolved (not from request)
    assert kwargs["org_id"] == ORG_ID
    assert kwargs["user_id"] == "user-42"
    assert kwargs["channel"] == "web"
    assert kwargs["agent_slug"] == "claw-main"


def test_agent_run_completed_via_proxy_dispatches():
    with patch(
        "jordan_claw.gateway.analytics_proxy.emitter.agent_run_completed",
        new=AsyncMock(),
    ) as mock_emit:
        client = TestClient(_app_with_token())
        resp = client.post(
            "/api/analytics/event",
            json={
                "event": "agent_run_completed",
                "distinct_id": "user-42",
                "properties": {
                    "agent_slug": "claw-main",
                    "run_kind": "user_message",
                    "channel": "web",
                    "model": "anthropic:claude-sonnet-5",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "duration_ms": 1200,
                    "tool_call_count": 0,
                    "success": True,
                },
            },
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

    assert resp.status_code == 202
    mock_emit.assert_awaited_once()
    kwargs = mock_emit.call_args.kwargs
    assert kwargs["run_kind"] == RunKind.USER_MESSAGE


def test_bad_run_kind_returns_400():
    client = TestClient(_app_with_token())
    resp = client.post(
        "/api/analytics/event",
        json={
            "event": "agent_run_completed",
            "distinct_id": "user-42",
            "properties": {
                "agent_slug": "claw-main",
                "run_kind": "not_a_kind",
                "channel": "web",
                "model": "anthropic:claude-sonnet-5",
                "input_tokens": 100,
                "output_tokens": 50,
                "duration_ms": 1200,
                "tool_call_count": 0,
                "success": True,
            },
        },
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert resp.status_code == 400


def test_bad_prop_type_returns_400():
    """A malformed prop type (cost_usd as a list) raises TypeError in the
    emitter (float(cost_usd)); the proxy must map that to 400, not 500."""
    client = TestClient(_app_with_token())
    resp = client.post(
        "/api/analytics/event",
        json={
            "event": "agent_run_completed",
            "distinct_id": "user-42",
            "properties": {
                "agent_slug": "claw-main",
                "run_kind": "user_message",
                "channel": "web",
                "model": "anthropic:claude-sonnet-5",
                "input_tokens": 100,
                "output_tokens": 50,
                "cost_usd": [1, 2],
                "duration_ms": 1200,
                "tool_call_count": 0,
                "success": True,
            },
        },
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert resp.status_code == 400


def test_missing_required_prop_returns_400():
    client = TestClient(_app_with_token())
    resp = client.post(
        "/api/analytics/event",
        json={
            "event": "agent_run_completed",
            "distinct_id": "user-42",
            "properties": {
                "agent_slug": "claw-main",
                "run_kind": "user_message",
                "channel": "web",
                "input_tokens": 100,
                "output_tokens": 50,
                "duration_ms": 1200,
                "tool_call_count": 0,
                "success": True,
            },
        },
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "missing_property: model"


def test_router_disabled_when_no_token():
    """If no frontend_analytics_token is configured, every request is 401."""
    client = TestClient(_app_with_token(token=None))
    resp = client.post(
        "/api/analytics/event",
        json={"event": "agent_session_started", "distinct_id": "u-1", "properties": {}},
        headers={"Authorization": "Bearer anything"},
    )
    assert resp.status_code == 401
