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
        "transcription_completed",
        "email_sent",
        "event_trigger_fired",
    }
    assert expected == emitter.ALLOWED_EVENTS


@pytest.mark.asyncio
async def test_agent_run_completed_emits_with_typed_props(mock_client):
    await emitter.agent_run_completed(
        org_id="org-1",
        user_id=None,
        agent_slug="claw-main",
        run_kind=RunKind.USER_MESSAGE,
        channel="app",
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
        error_severity=None,
        cache_read_tokens=30,
        cache_write_tokens=10,
    )
    await _drain()

    mock_client.capture.assert_called_once()
    kwargs = mock_client.capture.call_args.kwargs
    assert kwargs["event"] == "agent_run_completed"
    assert kwargs["distinct_id"] == "org-1"
    props = kwargs["properties"]
    assert props["agent_slug"] == "claw-main"
    assert props["run_kind"] == "user_message"
    assert props["channel"] == "app"
    assert props["conversation_id"] == "conv-1"
    assert props["model"] == "anthropic:claude-sonnet-4-5-20250929"
    assert props["input_tokens"] == 100
    assert props["output_tokens"] == 50
    assert props["cost_usd"] == 0.01
    assert props["duration_ms"] == 1234
    assert props["tool_call_count"] == 2
    assert props["success"] is True
    assert props["error_type"] is None
    assert props["error_severity"] is None
    assert props["cache_read_tokens"] == 30
    assert props["cache_write_tokens"] == 10


@pytest.mark.asyncio
async def test_agent_run_completed_includes_error_severity_on_failure(mock_client):
    await emitter.agent_run_completed(
        org_id="org-1",
        user_id=None,
        agent_slug="claw-main",
        run_kind=RunKind.USER_MESSAGE,
        channel="app",
        conversation_id="conv-1",
        schedule_name=None,
        model="anthropic:claude-sonnet-4-5-20250929",
        input_tokens=0,
        output_tokens=0,
        cost_usd=None,
        duration_ms=50,
        tool_call_count=0,
        success=False,
        error_type="timeout",
        error_severity="medium",
        cache_read_tokens=0,
        cache_write_tokens=0,
    )
    await _drain()

    props = mock_client.capture.call_args.kwargs["properties"]
    assert props["error_type"] == "timeout"
    assert props["error_severity"] == "medium"


@pytest.mark.asyncio
async def test_agent_run_completed_uses_user_id_when_provided(mock_client):
    await emitter.agent_run_completed(
        org_id="org-1",
        user_id="user-42",
        agent_slug="claw-main",
        run_kind=RunKind.USER_MESSAGE,
        channel="app",
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
        error_severity=None,
        cache_read_tokens=0,
        cache_write_tokens=0,
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
        channel="app",
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
    assert props["channel"] == "app"
    assert props["content_length"] == 120
    assert props["agent_slug"] == "claw-main"
    assert props["trigger"] == "scheduled"


@pytest.mark.asyncio
async def test_agent_session_started_emits(mock_client):
    await emitter.agent_session_started(
        org_id="org-1",
        user_id=None,
        channel="app",
        agent_slug="claw-main",
    )
    await _drain()

    kwargs = mock_client.capture.call_args.kwargs
    assert kwargs["event"] == "agent_session_started"
    assert kwargs["properties"] == {"channel": "app", "agent_slug": "claw-main"}


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
        cost_usd=0.0123,
        failures=1,
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
    assert props["cost_usd"] == 0.0123
    assert props["failures"] == 1


@pytest.mark.asyncio
async def test_eval_run_completed_handles_none_cost(mock_client):
    await emitter.eval_run_completed(
        dataset="obsidian_retrieval",
        total_cases=5,
        passed=5,
        score=1.0,
        prev_score=None,
        regression=False,
        duration_ms=1200,
        cost_usd=None,
        failures=0,
    )
    await _drain()

    props = mock_client.capture.call_args.kwargs["properties"]
    assert props["cost_usd"] is None
    assert props["failures"] == 0


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
async def test_transcription_completed_emits_with_typed_props(mock_client):
    await emitter.transcription_completed(
        org_id="org-1",
        duration_s=12.5,
        audio_bytes=2048,
        cost_usd=Decimal("0.00125"),
        latency_ms=850,
    )
    await _drain()

    mock_client.capture.assert_called_once()
    kwargs = mock_client.capture.call_args.kwargs
    assert kwargs["event"] == "transcription_completed"
    assert kwargs["distinct_id"] == "org-1"
    props = kwargs["properties"]
    assert props["duration_s"] == 12.5
    assert props["audio_bytes"] == 2048
    assert props["cost_usd"] == 0.00125
    assert props["latency_ms"] == 850


@pytest.mark.asyncio
async def test_transcription_completed_handles_none_duration_and_cost(mock_client):
    await emitter.transcription_completed(
        org_id="org-1",
        duration_s=None,
        audio_bytes=2048,
        cost_usd=None,
        latency_ms=850,
    )
    await _drain()

    props = mock_client.capture.call_args.kwargs["properties"]
    assert props["duration_s"] is None
    assert props["cost_usd"] is None


@pytest.mark.asyncio
async def test_email_sent_emits_send_props(mock_client):
    await emitter.email_sent(
        org_id="org-1",
        user_id=None,
        direction="send",
        message_id="msg-1",
        thread_id="th-1",
        body_length=42,
        subject_length=7,
    )
    await _drain()

    mock_client.capture.assert_called_once()
    kwargs = mock_client.capture.call_args.kwargs
    assert kwargs["event"] == "email_sent"
    assert kwargs["distinct_id"] == "org-1"
    props = kwargs["properties"]
    assert props["direction"] == "send"
    assert props["message_id"] == "msg-1"
    assert props["thread_id"] == "th-1"
    assert props["body_length"] == 42
    assert props["subject_length"] == 7


@pytest.mark.asyncio
async def test_email_sent_reply_has_no_subject_length(mock_client):
    await emitter.email_sent(
        org_id="org-1",
        user_id=None,
        direction="reply",
        message_id="msg-2",
        thread_id="th-1",
        body_length=10,
        subject_length=None,
    )
    await _drain()

    props = mock_client.capture.call_args.kwargs["properties"]
    assert props["direction"] == "reply"
    assert props["subject_length"] is None
    assert "subject" not in props
    assert "to" not in props


@pytest.mark.asyncio
async def test_event_trigger_fired_emits_fired_outcome(mock_client):
    await emitter.event_trigger_fired(
        org_id="org-1",
        user_id=None,
        trigger_name="inbound_email_review",
        source="fastmail-email",
        outcome="fired",
        cost_usd=Decimal("0.02"),
        input_tokens=100,
        output_tokens=50,
        duration_ms=900,
    )
    await _drain()

    mock_client.capture.assert_called_once()
    kwargs = mock_client.capture.call_args.kwargs
    assert kwargs["event"] == "event_trigger_fired"
    assert kwargs["distinct_id"] == "org-1"
    props = kwargs["properties"]
    assert props["trigger_name"] == "inbound_email_review"
    assert props["source"] == "fastmail-email"
    assert props["outcome"] == "fired"
    assert props["cost_usd"] == 0.02
    assert props["input_tokens"] == 100
    assert props["output_tokens"] == 50
    assert props["duration_ms"] == 900


@pytest.mark.asyncio
async def test_event_trigger_fired_nothing_to_send_outcome(mock_client):
    await emitter.event_trigger_fired(
        org_id="org-1",
        user_id=None,
        trigger_name="inbound_email_review",
        source="fastmail-email",
        outcome="nothing_to_send",
        cost_usd=None,
        input_tokens=10,
        output_tokens=5,
        duration_ms=200,
    )
    await _drain()

    props = mock_client.capture.call_args.kwargs["properties"]
    assert props["outcome"] == "nothing_to_send"
    assert props["cost_usd"] is None


@pytest.mark.asyncio
async def test_no_emit_when_client_none():
    """If get_posthog() returns None, emitter is a no-op (no exception)."""
    with patch("jordan_claw.analytics.emitter.get_posthog", return_value=None):
        await emitter.agent_session_started(
            org_id="org-1",
            user_id=None,
            channel="app",
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
        channel="app",
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
        channel="app",
        agent_slug="claw-main",
    )
    assert len(emitter._pending_tasks) >= 1

    await _drain()
    assert len(emitter._pending_tasks) == 0
    assert captured.is_set()
