from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from jordan_claw.analytics.types import RunKind
from jordan_claw.db.usage_events import most_recent_agent, save_usage_event

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
        channel="telegram",
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
    )

    db.table.assert_called_once_with("usage_events")
    insert_payload = query.insert.call_args[0][0]
    assert insert_payload["org_id"] == ORG_ID
    assert insert_payload["agent_slug"] == "claw-main"
    assert insert_payload["channel"] == "telegram"
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


@pytest.mark.asyncio
async def test_save_usage_event_failure_run():
    db, query = _mock_db(select_data=[{"id": "u1"}])

    await save_usage_event(
        db,
        org_id=ORG_ID,
        agent_slug="claw-main",
        conversation_id="conv-1",
        channel="telegram",
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
async def test_most_recent_agent_returns_slug():
    db, query = _mock_db(select_data=[{"agent_slug": "claw-main"}])

    result = await most_recent_agent(db, org_id=ORG_ID, channel="telegram")

    assert result == "claw-main"
    db.table.assert_called_once_with("usage_events")
    query.eq.assert_any_call("org_id", ORG_ID)
    query.eq.assert_any_call("channel", "telegram")
    query.eq.assert_any_call("run_kind", "user_message")


@pytest.mark.asyncio
async def test_most_recent_agent_returns_none_when_no_rows():
    db, _ = _mock_db(select_data=[])
    result = await most_recent_agent(db, org_id=ORG_ID, channel="telegram")
    assert result is None
