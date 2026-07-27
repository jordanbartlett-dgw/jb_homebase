from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
import structlog.testing

from jordan_claw.analytics.types import RunKind
from jordan_claw.db.usage_events import save_usage_event

ORG_ID = "00000000-0000-0000-0000-000000000001"


def _mock_db(select_data=None):
    mock_result = MagicMock(data=select_data or [])
    mock_query = MagicMock()
    mock_query.execute = AsyncMock(return_value=mock_result)
    mock_query.limit.return_value = mock_query
    mock_query.eq.return_value = mock_query
    mock_query.order.return_value = mock_query
    mock_query.select.return_value = mock_query
    mock_query.insert.return_value = mock_query
    mock_db = MagicMock()
    mock_db.table.return_value = mock_query
    return mock_db, mock_query


@pytest.mark.asyncio
async def test_save_usage_event_inserts_full_payload():
    db, query = _mock_db(select_data=[{"id": "u1"}])

    await save_usage_event(
        db,
        org_id=ORG_ID,
        agent_slug="claw-main",
        conversation_id="conv-1",
        channel="app",
        run_kind=RunKind.USER_MESSAGE,
        schedule_name=None,
        model="anthropic:claude-sonnet-4-5-20250929",
        input_tokens=1000,
        output_tokens=500,
        cost_usd=Decimal("0.012"),
        duration_ms=2500,
        tool_call_count=3,
        success=True,
        error_type=None,
        error_severity=None,
        trace_id="ab" * 16,
    )

    db.table.assert_called_once_with("usage_events")
    insert_payload = query.insert.call_args[0][0]
    assert insert_payload["trace_id"] == "ab" * 16
    assert insert_payload["org_id"] == ORG_ID
    assert insert_payload["agent_slug"] == "claw-main"
    assert insert_payload["channel"] == "app"
    assert insert_payload["run_kind"] == "user_message"
    assert insert_payload["input_tokens"] == 1000
    assert insert_payload["output_tokens"] == 500
    assert insert_payload["cost_usd"] == 0.012
    assert insert_payload["duration_ms"] == 2500
    assert insert_payload["tool_call_count"] == 3
    assert insert_payload["success"] is True


@pytest.mark.asyncio
async def test_save_usage_event_drops_none_fields():
    """None values shouldn't be sent — Postgres applies column defaults instead."""
    db, query = _mock_db(select_data=[{"id": "u1"}])

    await save_usage_event(
        db,
        org_id=ORG_ID,
        agent_slug="memory-extractor",
        conversation_id=None,
        channel="memory_extract",
        run_kind=RunKind.MEMORY_EXTRACT,
        schedule_name=None,
        model="anthropic:claude-haiku-4-5-20251001",
        input_tokens=200,
        output_tokens=50,
        cost_usd=None,
        duration_ms=800,
        tool_call_count=0,
        success=True,
        error_type=None,
        error_severity=None,
    )

    payload = query.insert.call_args[0][0]
    assert "cost_usd" not in payload
    assert "schedule_name" not in payload
    assert "conversation_id" not in payload
    assert "error_type" not in payload
    assert "error_severity" not in payload
    assert "trace_id" not in payload
    assert "cache_read_tokens" not in payload
    assert "cache_write_tokens" not in payload


@pytest.mark.asyncio
async def test_save_usage_event_includes_cache_tokens_when_provided():
    db, query = _mock_db(select_data=[{"id": "u1"}])

    await save_usage_event(
        db,
        org_id=ORG_ID,
        agent_slug="claw-main",
        conversation_id="conv-1",
        channel="app",
        run_kind=RunKind.USER_MESSAGE,
        schedule_name=None,
        model="anthropic:claude-sonnet-4-5-20250929",
        input_tokens=1000,
        output_tokens=200,
        cost_usd=Decimal("0.01"),
        duration_ms=1500,
        tool_call_count=1,
        success=True,
        error_type=None,
        error_severity=None,
        cache_read_tokens=300,
        cache_write_tokens=150,
    )

    payload = query.insert.call_args[0][0]
    assert payload["cache_read_tokens"] == 300
    assert payload["cache_write_tokens"] == 150


@pytest.mark.asyncio
async def test_save_usage_event_failure_run():
    db, query = _mock_db(select_data=[{"id": "u1"}])

    await save_usage_event(
        db,
        org_id=ORG_ID,
        agent_slug="claw-main",
        conversation_id="conv-1",
        channel="app",
        run_kind=RunKind.USER_MESSAGE,
        schedule_name=None,
        model="anthropic:claude-sonnet-4-5-20250929",
        input_tokens=0,
        output_tokens=0,
        cost_usd=None,
        duration_ms=120,
        tool_call_count=0,
        success=False,
        error_type="provider_overloaded",
        error_severity="medium",
    )

    payload = query.insert.call_args[0][0]
    assert payload["success"] is False
    assert payload["error_type"] == "provider_overloaded"
    assert payload["error_severity"] == "medium"


@pytest.mark.asyncio
async def test_save_usage_event_proactive_includes_schedule_name():
    db, query = _mock_db(select_data=[{"id": "u1"}])

    await save_usage_event(
        db,
        org_id=ORG_ID,
        agent_slug="claw-main",
        conversation_id=None,
        channel="proactive",
        run_kind=RunKind.PROACTIVE,
        schedule_name="morning_briefing",
        model="anthropic:claude-sonnet-4-5-20250929",
        input_tokens=500,
        output_tokens=200,
        cost_usd=Decimal("0.005"),
        duration_ms=1500,
        tool_call_count=2,
        success=True,
        error_type=None,
        error_severity=None,
    )

    payload = query.insert.call_args[0][0]
    assert payload["schedule_name"] == "morning_briefing"
    assert payload["run_kind"] == "proactive"


@pytest.mark.asyncio
async def test_save_usage_event_write_failure_logs_and_does_not_raise():
    """Fire-and-forget: a ledger write failure must never crash the caller."""
    db, query = _mock_db()
    query.execute = AsyncMock(side_effect=RuntimeError("db unreachable"))

    with structlog.testing.capture_logs() as cap_logs:
        await save_usage_event(
            db,
            org_id=ORG_ID,
            agent_slug="claw-main",
            conversation_id="conv-1",
            channel="app",
            run_kind=RunKind.USER_MESSAGE,
            schedule_name=None,
            model="anthropic:claude-sonnet-4-5-20250929",
            input_tokens=100,
            output_tokens=50,
            cost_usd=None,
            duration_ms=200,
            tool_call_count=0,
            success=True,
            error_type=None,
            error_severity=None,
        )

    warnings = [e for e in cap_logs if e.get("event") == "usage_event_write_failed"]
    assert len(warnings) == 1
    assert warnings[0]["agent_slug"] == "claw-main"
    assert warnings[0]["run_kind"] == "user_message"
    assert warnings[0]["error"] == "db unreachable"
