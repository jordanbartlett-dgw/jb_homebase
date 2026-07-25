from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from jordan_claw.db.health_log import (
    get_events_for_date,
    get_health_events_range,
    get_last_appointment_date,
    get_latest_health_event,
    insert_health_event,
    update_health_event,
)

ORG_ID = "org-001"


def _mock_db(select_data=None):
    """Mock Supabase async client with chained query builder (same pattern as test_db_workout)."""
    mock_result = MagicMock(data=select_data or [])

    mock_query = MagicMock()
    mock_query.execute = AsyncMock(return_value=mock_result)
    mock_query.limit.return_value = mock_query
    mock_query.eq.return_value = mock_query
    mock_query.order.return_value = mock_query
    mock_query.select.return_value = mock_query
    mock_query.insert.return_value = mock_query
    mock_query.update.return_value = mock_query
    mock_query.upsert.return_value = mock_query
    mock_query.gte.return_value = mock_query
    mock_query.lte.return_value = mock_query

    mock_db = MagicMock()
    mock_db.table.return_value = mock_query
    return mock_db, mock_query


_EVENT_ROW = {
    "id": "e1",
    "org_id": ORG_ID,
    "event_date": "2026-07-25",
    "category": "seizure",
    "title": "Brief tonic-clonic",
    "details": {"duration_sec": 45},
    "notes": "recovered quickly",
    "severity": "moderate",
    "logged_at": "2026-07-25T18:00:00+00:00",
}


@pytest.mark.asyncio
async def test_insert_health_event_defaults_details_and_omits_none_severity():
    db, query = _mock_db(select_data=[_EVENT_ROW])
    await insert_health_event(
        db,
        ORG_ID,
        event_date="2026-07-25",
        category="seizure",
        title="Brief tonic-clonic",
    )
    sent = query.insert.call_args[0][0]
    assert sent["org_id"] == ORG_ID
    assert sent["event_date"] == "2026-07-25"
    assert sent["category"] == "seizure"
    assert sent["title"] == "Brief tonic-clonic"
    assert sent["details"] == {}
    assert "severity" not in sent
    assert "notes" not in sent
    db.table.assert_called_with("health_events")


@pytest.mark.asyncio
async def test_insert_health_event_includes_provided_optional_fields():
    db, query = _mock_db(select_data=[_EVENT_ROW])
    await insert_health_event(
        db,
        ORG_ID,
        event_date="2026-07-25",
        category="seizure",
        title="Brief tonic-clonic",
        details={"duration_sec": 45},
        notes="recovered quickly",
        severity="moderate",
    )
    sent = query.insert.call_args[0][0]
    assert sent["details"] == {"duration_sec": 45}
    assert sent["notes"] == "recovered quickly"
    assert sent["severity"] == "moderate"


@pytest.mark.asyncio
async def test_get_events_for_date_filters_by_date():
    db, query = _mock_db(select_data=[_EVENT_ROW])
    events = await get_events_for_date(db, ORG_ID, "2026-07-25")
    assert events[0].id == "e1"
    query.eq.assert_any_call("event_date", "2026-07-25")
    query.eq.assert_any_call("org_id", ORG_ID)


@pytest.mark.asyncio
async def test_get_latest_health_event_orders_by_logged_at_desc():
    db, query = _mock_db(select_data=[_EVENT_ROW])
    event = await get_latest_health_event(db, ORG_ID)
    assert event is not None and event.id == "e1"
    query.order.assert_called_once_with("logged_at", desc=True)


@pytest.mark.asyncio
async def test_get_latest_health_event_none_when_empty():
    db, _ = _mock_db(select_data=[])
    assert await get_latest_health_event(db, ORG_ID) is None


@pytest.mark.asyncio
async def test_update_health_event_sends_only_provided_fields():
    db, query = _mock_db(select_data=[_EVENT_ROW])
    await update_health_event(db, ORG_ID, "e1", details={"duration_sec": 60})
    sent = query.update.call_args.args[0]
    assert sent == {"details": {"duration_sec": 60}}
    query.eq.assert_any_call("id", "e1")
    query.eq.assert_any_call("org_id", ORG_ID)


@pytest.mark.asyncio
async def test_get_health_events_range_orders_asc_no_category():
    db, query = _mock_db(select_data=[_EVENT_ROW])
    events = await get_health_events_range(db, ORG_ID, "2026-07-01", "2026-07-31")
    assert events[0].id == "e1"
    query.order.assert_called_once_with("event_date", desc=False)
    query.gte.assert_called_once_with("event_date", "2026-07-01")
    query.lte.assert_called_once_with("event_date", "2026-07-31")
    # No category filter applied: eq only called for org_id.
    assert query.eq.call_count == 1


@pytest.mark.asyncio
async def test_get_health_events_range_applies_category_filter():
    db, query = _mock_db(select_data=[_EVENT_ROW])
    await get_health_events_range(db, ORG_ID, "2026-07-01", "2026-07-31", category="seizure")
    query.eq.assert_any_call("category", "seizure")


@pytest.mark.asyncio
async def test_get_last_appointment_date_returns_none_when_empty():
    db, _ = _mock_db(select_data=[])
    assert await get_last_appointment_date(db, ORG_ID) is None


@pytest.mark.asyncio
async def test_get_last_appointment_date_filters_and_orders():
    db, query = _mock_db(select_data=[{**_EVENT_ROW, "category": "appointment"}])
    result = await get_last_appointment_date(db, ORG_ID)
    assert result == "2026-07-25"
    query.eq.assert_any_call("category", "appointment")
    query.order.assert_called_once_with("event_date", desc=True)
