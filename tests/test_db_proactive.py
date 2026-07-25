from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


def _mock_db(data: list[dict] | None = None) -> MagicMock:
    """Build a mock Supabase AsyncClient that returns given data."""
    db = MagicMock()
    result = MagicMock()
    result.data = data or []

    chain = MagicMock()
    chain.execute = AsyncMock(return_value=result)
    chain.eq.return_value = chain
    chain.select.return_value = chain
    chain.limit.return_value = chain
    chain.gte.return_value = chain
    chain.lt.return_value = chain
    chain.lte.return_value = chain
    chain.order.return_value = chain
    chain.insert.return_value = chain
    chain.update.return_value = chain
    db.table.return_value = chain

    return db


@pytest.mark.asyncio
async def test_get_enabled_schedules():
    from jordan_claw.db.proactive import get_enabled_schedules

    rows = [
        {
            "id": "s1",
            "org_id": "org-1",
            "name": "morning_briefing",
            "cron_expression": "0 7 * * *",
            "timezone": "America/Chicago",
            "enabled": True,
            "task_type": "morning_briefing",
            "config": {"agent_slug": "claw-main"},
            "last_run_at": None,
            "created_at": "2026-04-05T00:00:00+00:00",
        }
    ]
    db = _mock_db(rows)
    schedules = await get_enabled_schedules(db)
    assert len(schedules) == 1
    assert schedules[0].name == "morning_briefing"


@pytest.mark.asyncio
async def test_update_last_run():
    from jordan_claw.db.proactive import update_last_run

    db = MagicMock()
    chain = MagicMock()
    chain.execute = AsyncMock(return_value=MagicMock())
    chain.eq.return_value = chain
    db.table.return_value = MagicMock(update=MagicMock(return_value=chain))

    await update_last_run(db, "s1")
    db.table.assert_called_with("proactive_schedules")


@pytest.mark.asyncio
async def test_insert_proactive_message():
    from jordan_claw.db.proactive import insert_proactive_message

    db = MagicMock()
    chain = MagicMock()
    chain.execute = AsyncMock(return_value=MagicMock())
    db.table.return_value = MagicMock(insert=MagicMock(return_value=chain))

    await insert_proactive_message(
        db,
        org_id="org-1",
        task_type="morning_briefing",
        trigger="scheduled",
        content="Good morning!",
        schedule_id="s1",
    )
    db.table.assert_called_with("proactive_messages")


@pytest.mark.asyncio
async def test_get_latest_proactive_message_is_org_and_day_scoped():
    from datetime import UTC, datetime

    from jordan_claw.db.proactive import get_latest_proactive_message

    row = {
        "id": "brief-1",
        "task_type": "morning_briefing",
        "content": "Good morning!",
        "delivered_at": "2026-07-25T12:00:00+00:00",
    }
    db = _mock_db([row])
    query = db.table.return_value

    result = await get_latest_proactive_message(
        db,
        org_id="org-1",
        task_type="morning_briefing",
        delivered_from=datetime(2026, 7, 25, 5, 0, tzinfo=UTC),
        delivered_before=datetime(2026, 7, 26, 5, 0, tzinfo=UTC),
    )

    assert result == row
    query.eq.assert_any_call("org_id", "org-1")
    query.eq.assert_any_call("task_type", "morning_briefing")
    query.order.assert_called_once_with("delivered_at", desc=True)
    query.limit.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_was_sent_today_returns_true():
    from jordan_claw.db.proactive import was_sent_today

    db = _mock_db([{"id": "msg-1"}])
    result = await was_sent_today(db, "s1", "America/Chicago")
    assert result is True


@pytest.mark.asyncio
async def test_was_sent_today_returns_false():
    from jordan_claw.db.proactive import was_sent_today

    db = _mock_db([])
    result = await was_sent_today(db, "s1", "America/Chicago")
    assert result is False


@pytest.mark.asyncio
async def test_insert_reminder_schedule_shapes_row():
    from datetime import UTC, datetime

    from jordan_claw.db.proactive import insert_reminder_schedule

    inserted = {}

    db = MagicMock()
    chain = MagicMock()
    chain.execute = AsyncMock(return_value=MagicMock(data=[{"id": "r1"}]))

    def capture(row):
        inserted.update(row)
        return chain

    db.table.return_value = MagicMock(insert=capture)

    run_at = datetime(2026, 8, 1, 14, 0, 0, tzinfo=UTC)
    row = await insert_reminder_schedule(
        db,
        "org-1",
        message="Call the accountant",
        agent_slug="claw-main",
        run_at=run_at,
    )

    assert row == {"id": "r1"}
    assert inserted["source"] == "reminder"
    assert inserted["task_type"] == "reminder"
    assert inserted["run_at"] == run_at.isoformat()
    assert inserted["cron_expression"] is None
    assert inserted["config"] == {"message": "Call the accountant", "agent_slug": "claw-main"}
    assert inserted["name"].startswith("reminder-")


@pytest.mark.asyncio
async def test_list_reminder_schedules_filters_to_reminder_source():
    """list_reminders must never surface system jobs — the query itself
    filters on source='reminder' and enabled=true."""
    from jordan_claw.db.proactive import list_reminder_schedules

    row = {
        "id": "r1",
        "org_id": "org-1",
        "name": "reminder-abc",
        "cron_expression": None,
        "run_at": "2026-08-01T14:00:00+00:00",
        "timezone": "America/Chicago",
        "enabled": True,
        "task_type": "reminder",
        "config": {"message": "hi", "agent_slug": "claw-main"},
        "source": "reminder",
        "last_run_at": None,
        "created_at": "2026-07-25T00:00:00+00:00",
    }
    db = _mock_db([row])
    query = db.table.return_value

    reminders = await list_reminder_schedules(db, "org-1")

    assert len(reminders) == 1
    assert reminders[0].source == "reminder"
    query.eq.assert_any_call("source", "reminder")
    query.eq.assert_any_call("enabled", True)
    query.eq.assert_any_call("org_id", "org-1")


@pytest.mark.asyncio
async def test_disable_schedule():
    from jordan_claw.db.proactive import disable_schedule

    db = _mock_db()
    query = db.table.return_value
    await disable_schedule(db, "s1")
    db.table.assert_called_with("proactive_schedules")
    query.update.assert_called_once_with({"enabled": False})
    query.eq.assert_any_call("id", "s1")


@pytest.mark.asyncio
async def test_was_sent_within_true_and_false():
    from jordan_claw.db.proactive import was_sent_within

    assert await was_sent_within(_mock_db([{"id": "m1"}]), "s1", minutes=5) is True
    assert await was_sent_within(_mock_db([]), "s1", minutes=5) is False
