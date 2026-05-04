from __future__ import annotations

import asyncio
import time
from typing import Any

import logfire
import structlog
from pydantic_ai import Agent
from pydantic_ai.messages import ToolCallPart
from supabase._async.client import AsyncClient

from jordan_claw.analytics.types import AgentRunResult, RunKind
from jordan_claw.db.usage_events import save_usage_event
from jordan_claw.utils.pricing import compute_cost
from jordan_claw.utils.token_counting import extract_usage

log = structlog.get_logger()

DEFAULT_MAX_TOTAL_TOKENS = 200_000

_pending_writes: set[asyncio.Task] = set()


class TokenBudgetExceededError(Exception):
    """Raised when an agent run consumes more tokens than max_total_tokens."""


def classify_error(exc: BaseException) -> tuple[str, str]:
    """Map an exception to (error_type, error_severity).

    Severities follow the agent-observability taxonomy:
    low / medium / high / critical.
    """
    name = type(exc).__name__.lower()

    if isinstance(exc, TokenBudgetExceededError):
        return ("token_budget_exceeded", "high")
    if isinstance(exc, asyncio.TimeoutError) or "timeout" in name:
        return ("timeout", "medium")
    if "overloaded" in name or "overload" in name:
        return ("provider_overloaded", "medium")
    if "ratelimit" in name or "rate_limit" in name:
        return ("rate_limit", "medium")
    if "auth" in name or "permission" in name:
        return ("auth", "high")
    if isinstance(exc, ConnectionError) or "connection" in name:
        return ("network", "medium")
    if "tool" in name:
        return ("tool_error", "low")
    return ("unknown", "medium")


def _count_tool_calls(messages: list[Any]) -> int:
    count = 0
    for msg in messages:
        for part in getattr(msg, "parts", ()):
            if isinstance(part, ToolCallPart):
                count += 1
    return count


def _fire_save(coro) -> None:
    task = asyncio.create_task(coro, name="usage-event-write")
    _pending_writes.add(task)
    task.add_done_callback(_pending_writes.discard)


async def drain_pending_writes() -> None:
    """Wait for all in-flight usage_events writes to complete.

    Used by tests for deterministic assertions and by graceful shutdown.
    """
    if _pending_writes:
        await asyncio.gather(*list(_pending_writes), return_exceptions=True)


async def run_agent_instrumented[OutputT](
    *,
    agent: Agent[Any, OutputT],
    prompt: str,
    deps: Any,
    db: AsyncClient,
    org_id: str,
    agent_slug: str,
    model: str,
    run_kind: RunKind,
    channel: str,
    conversation_id: str | None = None,
    schedule_name: str | None = None,
    message_history: list | None = None,
    max_total_tokens: int = DEFAULT_MAX_TOTAL_TOKENS,
) -> AgentRunResult[OutputT]:
    """Run an agent with full instrumentation.

    Wraps `agent.run(...)` with:
    - Logfire parent span carrying agent_slug / channel / run_kind / etc.
    - Latency timing
    - Usage + cost extraction
    - Tool-call counting via ToolCallPart
    - Token-budget guardrail (raises TokenBudgetExceeded on over-budget)
    - Error classification
    - Fire-and-forget usage_events insert
    """
    span_attrs = {
        "agent_slug": agent_slug,
        "channel": channel,
        "run_kind": run_kind.value,
        "conversation_id": conversation_id,
        "schedule_name": schedule_name,
        "model": model,
        "org_id": org_id,
    }

    with logfire.span("agent_run", **span_attrs) as span:
        start = time.monotonic()
        try:
            run_kwargs: dict[str, Any] = {}
            if deps is not None:
                run_kwargs["deps"] = deps
            if message_history is not None:
                run_kwargs["message_history"] = message_history

            result = await agent.run(prompt, **run_kwargs)

        except Exception as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            error_type, error_severity = classify_error(exc)
            span.set_attribute("usage.duration_ms", duration_ms)
            span.set_attribute("outcome.success", False)
            span.set_attribute("outcome.error_type", error_type)
            log.exception(
                "agent_run_failed",
                agent_slug=agent_slug,
                run_kind=run_kind.value,
                channel=channel,
                error_type=error_type,
                duration_ms=duration_ms,
            )
            _fire_save(
                save_usage_event(
                    db,
                    org_id=org_id,
                    agent_slug=agent_slug,
                    conversation_id=conversation_id,
                    channel=channel,
                    run_kind=run_kind,
                    schedule_name=schedule_name,
                    model=model,
                    input_tokens=0,
                    output_tokens=0,
                    cost_usd=None,
                    duration_ms=duration_ms,
                    tool_call_count=0,
                    success=False,
                    error_type=error_type,
                    error_severity=error_severity,
                )
            )
            raise

        duration_ms = int((time.monotonic() - start) * 1000)
        usage = extract_usage(result.usage())
        tool_call_count = _count_tool_calls(result.all_messages())
        cost = compute_cost(model, usage["input_tokens"], usage["output_tokens"])

        if usage["total_tokens"] > max_total_tokens:
            log.warning(
                "agent_run_token_exceeded",
                agent_slug=agent_slug,
                total_tokens=usage["total_tokens"],
                budget=max_total_tokens,
            )
            span.set_attribute("usage.input_tokens", usage["input_tokens"])
            span.set_attribute("usage.output_tokens", usage["output_tokens"])
            span.set_attribute("usage.duration_ms", duration_ms)
            span.set_attribute("outcome.success", False)
            span.set_attribute("outcome.error_type", "token_budget_exceeded")
            _fire_save(
                save_usage_event(
                    db,
                    org_id=org_id,
                    agent_slug=agent_slug,
                    conversation_id=conversation_id,
                    channel=channel,
                    run_kind=run_kind,
                    schedule_name=schedule_name,
                    model=model,
                    input_tokens=usage["input_tokens"],
                    output_tokens=usage["output_tokens"],
                    cost_usd=cost,
                    duration_ms=duration_ms,
                    tool_call_count=tool_call_count,
                    success=False,
                    error_type="token_budget_exceeded",
                    error_severity="high",
                )
            )
            raise TokenBudgetExceededError(
                f"agent_run total_tokens={usage['total_tokens']} > budget={max_total_tokens}"
            )

        span.set_attribute("usage.input_tokens", usage["input_tokens"])
        span.set_attribute("usage.output_tokens", usage["output_tokens"])
        span.set_attribute("usage.cost_usd", float(cost) if cost is not None else None)
        span.set_attribute("usage.duration_ms", duration_ms)
        span.set_attribute("usage.tool_call_count", tool_call_count)
        span.set_attribute("outcome.success", True)

        _fire_save(
            save_usage_event(
                db,
                org_id=org_id,
                agent_slug=agent_slug,
                conversation_id=conversation_id,
                channel=channel,
                run_kind=run_kind,
                schedule_name=schedule_name,
                model=model,
                input_tokens=usage["input_tokens"],
                output_tokens=usage["output_tokens"],
                cost_usd=cost,
                duration_ms=duration_ms,
                tool_call_count=tool_call_count,
                success=True,
                error_type=None,
                error_severity=None,
            )
        )

        return AgentRunResult(
            output=result.output,
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            total_tokens=usage["total_tokens"],
            cost_usd=cost,
            duration_ms=duration_ms,
            tool_call_count=tool_call_count,
            model=model,
            success=True,
            error_type=None,
        )
