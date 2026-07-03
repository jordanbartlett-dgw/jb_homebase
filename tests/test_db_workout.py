from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from jordan_claw.db.workout import (
    get_active_plan,
    get_recent_workout_logs,
    get_workout_profile,
    insert_workout_log,
    save_workout_plan,
    upsert_workout_profile,
)
from jordan_claw.workout.models import PlanDay, PlanWeek

ORG_ID = "org-001"


def _mock_db(select_data=None):
    """Mock Supabase async client with chained query builder (same pattern as test_db_memory)."""
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

    mock_db = MagicMock()
    mock_db.table.return_value = mock_query
    return mock_db, mock_query


@pytest.mark.asyncio
async def test_get_workout_profile_none_when_missing():
    db, _ = _mock_db(select_data=[])
    assert await get_workout_profile(db, ORG_ID) is None


@pytest.mark.asyncio
async def test_get_workout_profile_returns_model():
    db, _ = _mock_db(select_data=[{"org_id": ORG_ID, "experience": "intermediate"}])
    profile = await get_workout_profile(db, ORG_ID)
    assert profile.experience == "intermediate"
    db.table.assert_called_with("workout_profiles")


@pytest.mark.asyncio
async def test_upsert_workout_profile_only_sends_provided_fields():
    db, query = _mock_db()
    await upsert_workout_profile(db, ORG_ID, experience="beginner")
    sent = query.upsert.call_args[0][0]
    assert sent["experience"] == "beginner"
    assert sent["org_id"] == ORG_ID
    assert "goals" not in sent
    assert query.upsert.call_args.kwargs["on_conflict"] == "org_id"


@pytest.mark.asyncio
async def test_get_active_plan_none_when_missing():
    db, _ = _mock_db(select_data=[])
    assert await get_active_plan(db, ORG_ID) is None


@pytest.mark.asyncio
async def test_get_active_plan_returns_model():
    db, query = _mock_db(select_data=[{
        "id": "p1", "org_id": ORG_ID, "status": "active",
        "starts_on": "2026-07-07", "weeks": [], "rationale": "Base",
    }])
    plan = await get_active_plan(db, ORG_ID)
    assert plan.status == "active"
    query.eq.assert_any_call("status", "active")


@pytest.mark.asyncio
async def test_save_workout_plan_archives_then_inserts():
    db, query = _mock_db(select_data=[{"id": "p2"}])
    weeks = [
        PlanWeek(
            week_number=1,
            days=[PlanDay(day="monday", session_type="run", description="Easy 4mi")],
        )
    ]
    row = await save_workout_plan(
        db, ORG_ID, starts_on="2026-07-07", weeks=weeks, rationale="Base"
    )
    assert row["id"] == "p2"
    query.update.assert_called_once_with({"status": "archived"})
    inserted = query.insert.call_args[0][0]
    assert inserted["weeks"][0]["days"][0]["session_type"] == "run"


@pytest.mark.asyncio
async def test_insert_workout_log():
    db, query = _mock_db(select_data=[{"id": "l1"}])
    await insert_workout_log(
        db, ORG_ID, logged_date="2026-07-03", activity="run",
        details={"distance_mi": 5}, notes="legs heavy",
    )
    sent = query.insert.call_args[0][0]
    assert sent["activity"] == "run"
    assert sent["details"] == {"distance_mi": 5}


@pytest.mark.asyncio
async def test_get_recent_workout_logs_ordered_desc():
    db, query = _mock_db(select_data=[
        {"id": "l1", "org_id": ORG_ID, "logged_date": "2026-07-02", "activity": "run"},
    ])
    logs = await get_recent_workout_logs(db, ORG_ID, limit=7)
    assert logs[0].activity == "run"
    query.order.assert_called_once_with("logged_date", desc=True)
