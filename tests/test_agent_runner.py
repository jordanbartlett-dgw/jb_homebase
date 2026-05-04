from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai import Agent

from jordan_claw.analytics.types import AgentRunResult, RunKind
from jordan_claw.utils.agent_runner import (
    TokenBudgetExceededError,
    classify_error,
    drain_pending_writes,
    run_agent_instrumented,
)

ORG_ID = "00000000-0000-0000-0000-000000000001"


def _mock_db():
    query = MagicMock()
    query.execute = AsyncMock(return_value=MagicMock(data=[{"id": "u1"}]))
    query.insert.return_value = query
    db = MagicMock()
    db.table.return_value = query
    return db, query


@pytest.mark.asyncio
async def test_happy_path_returns_agent_run_result():
    agent = Agent("test")
    db, _ = _mock_db()

    result = await run_agent_instrumented(
        agent=agent,
        prompt="hello",
        deps=None,
        db=db,
        org_id=ORG_ID,
        agent_slug="claw-main",
        model="anthropic:claude-sonnet-4-5-20250929",
        run_kind=RunKind.USER_MESSAGE,
        channel="telegram",
        conversation_id="conv-1",
    )

    assert isinstance(result, AgentRunResult)
    assert result.success is True
    assert result.error_type is None
    assert result.duration_ms >= 0
    assert result.input_tokens >= 0
    assert result.output_tokens >= 0
    assert result.tool_call_count >= 0
    assert result.model == "anthropic:claude-sonnet-4-5-20250929"


@pytest.mark.asyncio
async def test_happy_path_writes_usage_event():
    agent = Agent("test")
    db, query = _mock_db()

    with patch("jordan_claw.utils.agent_runner.compute_cost", return_value=Decimal("0.01")):
        await run_agent_instrumented(
            agent=agent,
            prompt="hello",
            deps=None,
            db=db,
            org_id=ORG_ID,
            agent_slug="claw-main",
            model="anthropic:claude-sonnet-4-5-20250929",
            run_kind=RunKind.USER_MESSAGE,
            channel="telegram",
            conversation_id="conv-1",
        )

    await drain_pending_writes()
    db.table.assert_called_with("usage_events")
    payload = query.insert.call_args[0][0]
    assert payload["agent_slug"] == "claw-main"
    assert payload["run_kind"] == "user_message"
    assert payload["success"] is True


@pytest.mark.asyncio
async def test_proactive_run_kind_writes_schedule_name():
    agent = Agent("test")
    db, query = _mock_db()

    await run_agent_instrumented(
        agent=agent,
        prompt="brief me",
        deps=None,
        db=db,
        org_id=ORG_ID,
        agent_slug="claw-main",
        model="anthropic:claude-sonnet-4-5-20250929",
        run_kind=RunKind.PROACTIVE,
        channel="proactive",
        schedule_name="morning_briefing",
    )

    await drain_pending_writes()
    payload = query.insert.call_args[0][0]
    assert payload["run_kind"] == "proactive"
    assert payload["schedule_name"] == "morning_briefing"
    assert payload["channel"] == "proactive"


@pytest.mark.asyncio
async def test_exception_classified_and_reraised():
    agent = MagicMock()
    agent.run = AsyncMock(side_effect=TimeoutError("upstream timeout"))
    db, query = _mock_db()

    with pytest.raises(TimeoutError):
        await run_agent_instrumented(
            agent=agent,
            prompt="hello",
            deps=None,
            db=db,
            org_id=ORG_ID,
            agent_slug="claw-main",
            model="anthropic:claude-sonnet-4-5-20250929",
            run_kind=RunKind.USER_MESSAGE,
            channel="telegram",
            conversation_id="conv-1",
        )

    await drain_pending_writes()
    payload = query.insert.call_args[0][0]
    assert payload["success"] is False
    assert payload["error_type"] == "timeout"


@pytest.mark.asyncio
async def test_token_budget_exceeded_raises_and_records_failure():
    agent = MagicMock()
    fake_usage = MagicMock(input_tokens=200_000, output_tokens=10_000, requests=1)
    fake_result = MagicMock()
    fake_result.output = "long output"
    fake_result.usage = MagicMock(return_value=fake_usage)
    fake_result.all_messages = MagicMock(return_value=[])
    agent.run = AsyncMock(return_value=fake_result)
    db, query = _mock_db()

    with pytest.raises(TokenBudgetExceededError):
        await run_agent_instrumented(
            agent=agent,
            prompt="hello",
            deps=None,
            db=db,
            org_id=ORG_ID,
            agent_slug="claw-main",
            model="anthropic:claude-sonnet-4-5-20250929",
            run_kind=RunKind.USER_MESSAGE,
            channel="telegram",
            conversation_id="conv-1",
            max_total_tokens=100_000,
        )

    await drain_pending_writes()
    payload = query.insert.call_args[0][0]
    assert payload["success"] is False
    assert payload["error_type"] == "token_budget_exceeded"


@pytest.mark.asyncio
async def test_tool_call_count_extracted_from_messages():
    """Wrapper should count ToolCallPart instances across all messages."""
    from pydantic_ai.messages import ModelResponse, ToolCallPart

    agent = MagicMock()
    fake_usage = MagicMock(input_tokens=100, output_tokens=50, requests=2)
    fake_msg = ModelResponse(
        parts=[
            ToolCallPart(tool_name="search_web", args={"q": "x"}, tool_call_id="t1"),
            ToolCallPart(tool_name="search_web", args={"q": "y"}, tool_call_id="t2"),
        ],
        model_name="anthropic:claude-sonnet-4-5-20250929",
    )
    fake_result = MagicMock()
    fake_result.output = "done"
    fake_result.usage = MagicMock(return_value=fake_usage)
    fake_result.all_messages = MagicMock(return_value=[fake_msg])
    agent.run = AsyncMock(return_value=fake_result)
    db, _ = _mock_db()

    result = await run_agent_instrumented(
        agent=agent,
        prompt="hello",
        deps=None,
        db=db,
        org_id=ORG_ID,
        agent_slug="claw-main",
        model="anthropic:claude-sonnet-4-5-20250929",
        run_kind=RunKind.USER_MESSAGE,
        channel="telegram",
        conversation_id="conv-1",
    )

    assert result.tool_call_count == 2


def test_classify_error_known_signatures():
    assert classify_error(TimeoutError("x")) == ("timeout", "medium")
    assert classify_error(ConnectionError("x")) == ("network", "medium")


def test_classify_error_anthropic_overloaded():
    err = type("OverloadedError", (Exception,), {})("overloaded")
    assert classify_error(err)[0] == "provider_overloaded"


def test_classify_error_unknown_falls_back():
    err = ValueError("something weird")
    kind, severity = classify_error(err)
    assert kind == "unknown"
    assert severity in ("low", "medium", "high", "critical")
