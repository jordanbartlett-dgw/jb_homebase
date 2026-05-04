from __future__ import annotations

import asyncio
from decimal import Decimal

import structlog

from jordan_claw.analytics.posthog_client import get_posthog
from jordan_claw.analytics.types import RunKind

log = structlog.get_logger()

ALLOWED_EVENTS: set[str] = {
    "agent_run_completed",
    "proactive_sent",
    "agent_session_started",
    "eval_run_completed",
    "feedback_submitted",
}

_pending_tasks: set[asyncio.Task] = set()


def _resolve_distinct_id(user_id: str | None, org_id: str) -> str:
    """Today single-user → user_id when present, else org_id."""
    return user_id or org_id


def _capture(event: str, distinct_id: str, props: dict) -> None:
    client = get_posthog()
    if client is None:
        return
    try:
        client.capture(distinct_id=distinct_id, event=event, properties=props)
    except Exception:
        log.warning("posthog_capture_failed", event=event, exc_info=True)


def _fire(event: str, distinct_id: str, props: dict) -> None:
    """Fire-and-forget capture. Survives GC via _pending_tasks."""
    if get_posthog() is None:
        return
    task = asyncio.create_task(
        asyncio.to_thread(_capture, event, distinct_id, props),
        name=f"posthog-{event}",
    )
    _pending_tasks.add(task)
    task.add_done_callback(_pending_tasks.discard)


async def drain_pending_emits() -> None:
    """Wait for all in-flight PostHog captures. Used by shutdown + tests."""
    if _pending_tasks:
        await asyncio.gather(*list(_pending_tasks), return_exceptions=True)


async def agent_run_completed(
    *,
    org_id: str,
    user_id: str | None,
    agent_slug: str,
    run_kind: RunKind,
    channel: str,
    conversation_id: str | None,
    schedule_name: str | None,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: Decimal | None,
    duration_ms: int,
    tool_call_count: int,
    success: bool,
    error_type: str | None,
) -> None:
    props = {
        "agent_slug": agent_slug,
        "run_kind": run_kind.value,
        "channel": channel,
        "conversation_id": conversation_id,
        "schedule_name": schedule_name,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": float(cost_usd) if cost_usd is not None else None,
        "duration_ms": duration_ms,
        "tool_call_count": tool_call_count,
        "success": success,
        "error_type": error_type,
    }
    _fire("agent_run_completed", _resolve_distinct_id(user_id, org_id), props)


async def proactive_sent(
    *,
    org_id: str,
    user_id: str | None,
    schedule_name: str | None,
    task_type: str,
    channel: str,
    content_length: int,
    agent_slug: str | None,
    trigger: str,
) -> None:
    props = {
        "schedule_name": schedule_name,
        "task_type": task_type,
        "channel": channel,
        "content_length": content_length,
        "agent_slug": agent_slug,
        "trigger": trigger,
    }
    _fire("proactive_sent", _resolve_distinct_id(user_id, org_id), props)


async def agent_session_started(
    *,
    org_id: str,
    user_id: str | None,
    channel: str,
    agent_slug: str,
) -> None:
    props = {"channel": channel, "agent_slug": agent_slug}
    _fire("agent_session_started", _resolve_distinct_id(user_id, org_id), props)


async def eval_run_completed(
    *,
    dataset: str,
    total_cases: int,
    passed: int,
    score: float,
    prev_score: float | None,
    regression: bool,
    duration_ms: int,
) -> None:
    props = {
        "dataset": dataset,
        "total_cases": total_cases,
        "passed": passed,
        "score": score,
        "prev_score": prev_score,
        "regression": regression,
        "duration_ms": duration_ms,
    }
    _fire("eval_run_completed", "system:eval", props)


async def feedback_submitted(
    *,
    org_id: str,
    user_id: str | None,
    agent_slug: str,
    rating: int,
    has_note: bool,
    prompt_source: str,
    conversation_id: str | None,
) -> None:
    props = {
        "agent_slug": agent_slug,
        "rating": rating,
        "has_note": has_note,
        "prompt_source": prompt_source,
        "conversation_id": conversation_id,
    }
    _fire("feedback_submitted", _resolve_distinct_id(user_id, org_id), props)
