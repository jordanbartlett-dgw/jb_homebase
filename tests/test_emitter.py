from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from jordan_claw.analytics import emitter
from jordan_claw.analytics.types import RunKind


@pytest.fixture
def mock_client():
    """Patch get_posthog to return a MagicMock; assert capture calls."""
    client = MagicMock()
    with patch("jordan_claw.analytics.emitter.get_posthog", return_value=client):
        yield client


async def _drain() -> None:
    await emitter.drain_pending_emits()


def test_allowed_events_matches_emitter_function_names():
    expected = {
        "agent_run_completed",
        "proactive_sent",
        "agent_session_started",
        "eval_run_completed",
        "feedback_submitted",
    }
    assert expected == emitter.ALLOWED_EVENTS


@pytest.mark.asyncio
async def test_agent_run_completed_emits_with_typed_props(mock_client):
    await emitter.agent_run_completed(
        org_id="org-1",
        user_id=None,
        agent_slug="claw-main",
        run_kind=RunKind.USER_MESSAGE,
        channel="telegram",
        conversation_id="conv-1",
        schedule_name=None,
        model="anthropic:claude-sonnet-4-5-20250929",
        input_tokens=100,
        output_tokens=50,
        cost_usd=Decimal("0.01"),
        duration_ms=1234,
        tool_call_count=2,
        success=True,
        error_type=None,
    )
    await _drain()

    mock_client.capture.assert_called_once()
    kwargs = mock_client.capture.call_args.kwargs
    assert kwargs["event"] == "agent_run_completed"
    assert kwargs["distinct_id"] == "org-1"
    props = kwargs["properties"]
    assert props["agent_slug"] == "claw-main"
    assert props["run_kind"] == "user_message"
    assert props["channel"] == "telegram"
    assert props["conversation_id"] == "conv-1"
    assert props["model"] == "anthropic:claude-sonnet-4-5-20250929"
    assert props["input_tokens"] == 100
    assert props["output_tokens"] == 50
    assert props["cost_usd"] == 0.01
    assert props["duration_ms"] == 1234
    assert props["tool_call_count"] == 2
    assert props["success"] is True
    assert props["error_type"] is None


@pytest.mark.asyncio
async def test_agent_run_completed_uses_user_id_when_provided(mock_client):
    await emitter.agent_run_completed(
        org_id="org-1",
        user_id="user-42",
        agent_slug="claw-main",
        run_kind=RunKind.USER_MESSAGE,
        channel="telegram",
        conversation_id=None,
        schedule_name=None,
        model="m",
        input_tokens=1,
        output_tokens=1,
        cost_usd=None,
        duration_ms=1,
        tool_call_count=0,
        success=True,
        error_type=None,
    )
    await _drain()

    assert mock_client.capture.call_args.kwargs["distinct_id"] == "user-42"


@pytest.mark.asyncio
async def test_proactive_sent_emits(mock_client):
    await emitter.proactive_sent(
        org_id="org-1",
        user_id=None,
        schedule_name="morning_briefing",
        task_type="briefing",
        channel="telegram",
        content_length=120,
        agent_slug="claw-main",
        trigger="scheduled",
    )
    await _drain()

    mock_client.capture.assert_called_once()
    kwargs = mock_client.capture.call_args.kwargs
    assert kwargs["event"] == "proactive_sent"
    props = kwargs["properties"]
    assert props["schedule_name"] == "morning_briefing"
    assert props["task_type"] == "briefing"
    assert props["channel"] == "telegram"
    assert props["content_length"] == 120
    assert props["agent_slug"] == "claw-main"
    assert props["trigger"] == "scheduled"


@pytest.mark.asyncio
async def test_agent_session_started_emits(mock_client):
    await emitter.agent_session_started(
        org_id="org-1",
        user_id=None,
        channel="telegram",
        agent_slug="claw-main",
    )
    await _drain()

    kwargs = mock_client.capture.call_args.kwargs
    assert kwargs["event"] == "agent_session_started"
    assert kwargs["properties"] == {"channel": "telegram", "agent_slug": "claw-main"}


@pytest.mark.asyncio
async def test_eval_run_completed_uses_system_distinct_id(mock_client):
    await emitter.eval_run_completed(
        dataset="memory_recall",
        total_cases=10,
        passed=9,
        score=0.9,
        prev_score=0.85,
        regression=False,
        duration_ms=5000,
    )
    await _drain()

    kwargs = mock_client.capture.call_args.kwargs
    assert kwargs["event"] == "eval_run_completed"
    assert kwargs["distinct_id"] == "system:eval"
    props = kwargs["properties"]
    assert props["dataset"] == "memory_recall"
    assert props["total_cases"] == 10
    assert props["passed"] == 9
    assert props["score"] == 0.9
    assert props["prev_score"] == 0.85
    assert props["regression"] is False
    assert props["duration_ms"] == 5000


@pytest.mark.asyncio
async def test_feedback_submitted_emits(mock_client):
    await emitter.feedback_submitted(
        org_id="org-1",
        user_id=None,
        agent_slug="claw-main",
        rating=5,
        has_note=True,
        prompt_source="manual",
        conversation_id="conv-1",
    )
    await _drain()

    kwargs = mock_client.capture.call_args.kwargs
    assert kwargs["event"] == "feedback_submitted"
    props = kwargs["properties"]
    assert props["agent_slug"] == "claw-main"
    assert props["rating"] == 5
    assert props["has_note"] is True
    assert props["prompt_source"] == "manual"
    assert props["conversation_id"] == "conv-1"


@pytest.mark.asyncio
async def test_no_emit_when_client_none():
    """If get_posthog() returns None, emitter is a no-op (no exception)."""
    with patch("jordan_claw.analytics.emitter.get_posthog", return_value=None):
        await emitter.agent_session_started(
            org_id="org-1",
            user_id=None,
            channel="telegram",
            agent_slug="claw-main",
        )
        await _drain()


@pytest.mark.asyncio
async def test_capture_exception_swallowed(mock_client):
    """A failing PostHog client must NOT raise into the caller."""
    mock_client.capture.side_effect = RuntimeError("posthog down")

    await emitter.agent_session_started(
        org_id="org-1",
        user_id=None,
        channel="telegram",
        agent_slug="claw-main",
    )
    await _drain()

    mock_client.capture.assert_called_once()


@pytest.mark.asyncio
async def test_pending_tasks_tracked(mock_client):
    """In-flight tasks must be retained in a set so the GC can't drop them mid-flush."""
    captured = asyncio.Event()
    mock_client.capture.side_effect = lambda **kw: captured.set()

    await emitter.agent_session_started(
        org_id="org-1",
        user_id=None,
        channel="telegram",
        agent_slug="claw-main",
    )
    assert len(emitter._pending_tasks) >= 1

    await _drain()
    assert len(emitter._pending_tasks) == 0
    assert captured.is_set()
