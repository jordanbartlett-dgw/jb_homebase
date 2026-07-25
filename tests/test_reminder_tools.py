from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jordan_claw.proactive.models import ProactiveSchedule
from jordan_claw.tools.reminders import CENTRAL_TZ, cancel_reminder, list_reminders, set_reminder


def _make_ctx(org_id: str = "org-001"):
    ctx = MagicMock()
    ctx.deps.org_id = org_id
    ctx.deps.supabase_client = MagicMock()
    return ctx


def _schedule_row(
    schedule_id: str = "r1",
    org_id: str = "org-001",
    source: str = "reminder",
    enabled: bool = True,
    cron: str | None = None,
    run_at: str | None = "2026-08-01T14:00:00+00:00",
    message: str = "Call the accountant",
) -> dict:
    return {
        "id": schedule_id,
        "org_id": org_id,
        "name": f"reminder-{schedule_id}",
        "cron_expression": cron,
        "run_at": run_at,
        "timezone": "America/Chicago",
        "enabled": enabled,
        "task_type": "reminder",
        "config": {"message": message, "agent_slug": "claw-main"},
        "source": source,
        "last_run_at": None,
        "created_at": "2026-07-25T00:00:00+00:00",
    }


@pytest.mark.asyncio
async def test_set_reminder_requires_exactly_one_of_run_at_and_cron():
    ctx = _make_ctx()
    future = datetime.now(CENTRAL_TZ) + timedelta(hours=1)

    neither = await set_reminder(ctx, "hi")
    both = await set_reminder(ctx, "hi", run_at=future, cron="0 9 * * *")

    assert neither.startswith("Not set")
    assert both.startswith("Not set")


@pytest.mark.asyncio
async def test_set_reminder_rejects_past_run_at():
    ctx = _make_ctx()
    past = datetime.now(CENTRAL_TZ) - timedelta(hours=1)
    result = await set_reminder(ctx, "hi", run_at=past)
    assert result.startswith("Not set")
    assert "in the past" in result


@pytest.mark.asyncio
async def test_set_reminder_rejects_bad_cron():
    ctx = _make_ctx()
    result = await set_reminder(ctx, "hi", cron="not a cron")
    assert result.startswith("Not set")


@pytest.mark.asyncio
async def test_set_reminder_one_shot_naive_time_becomes_central():
    """A naive run_at from the model is interpreted as US Central."""
    ctx = _make_ctx()
    naive_future = (datetime.now(CENTRAL_TZ) + timedelta(hours=2)).replace(tzinfo=None)

    mock_insert = AsyncMock(return_value=_schedule_row())
    with patch("jordan_claw.tools.reminders.insert_reminder_schedule", mock_insert):
        result = await set_reminder(ctx, "Call the accountant", run_at=naive_future)

    assert "Reminder set" in result
    stored = mock_insert.call_args.kwargs["run_at"]
    assert stored.tzinfo is not None
    assert stored.utcoffset() == naive_future.replace(tzinfo=CENTRAL_TZ).utcoffset()


@pytest.mark.asyncio
async def test_set_reminder_cron_reports_sane_next_run():
    ctx = _make_ctx()
    row = _schedule_row(cron="0 9 * * *", run_at=None)

    with patch(
        "jordan_claw.tools.reminders.insert_reminder_schedule",
        AsyncMock(return_value=row),
    ):
        result = await set_reminder(ctx, "Drink water", cron="0 9 * * *")

    assert "Reminder set" in result
    assert "09:00" in result
    assert "recurring: 0 9 * * *" in result


@pytest.mark.asyncio
async def test_list_reminders_formats_pending_rows():
    ctx = _make_ctx()
    rows = [
        ProactiveSchedule.model_validate(_schedule_row()),
        ProactiveSchedule.model_validate(
            _schedule_row(schedule_id="r2", cron="0 9 * * 1", run_at=None, message="Weekly plan")
        ),
    ]
    with patch(
        "jordan_claw.tools.reminders.list_reminder_schedules",
        AsyncMock(return_value=rows),
    ) as mock_list:
        result = await list_reminders(ctx)

    # Filtering to source='reminder' lives in list_reminder_schedules;
    # test_db_proactive covers the query. Here: both rows render with ids.
    mock_list.assert_awaited_once_with(ctx.deps.supabase_client, "org-001")
    assert "r1" in result and "Call the accountant" in result
    assert "r2" in result and "Weekly plan" in result


@pytest.mark.asyncio
async def test_list_reminders_empty():
    ctx = _make_ctx()
    with patch(
        "jordan_claw.tools.reminders.list_reminder_schedules",
        AsyncMock(return_value=[]),
    ):
        assert await list_reminders(ctx) == "No pending reminders."


@pytest.mark.asyncio
async def test_cancel_reminder_disables_row():
    ctx = _make_ctx()
    schedule = ProactiveSchedule.model_validate(_schedule_row())
    mock_disable = AsyncMock()
    with (
        patch("jordan_claw.tools.reminders.get_schedule", AsyncMock(return_value=schedule)),
        patch("jordan_claw.tools.reminders.disable_schedule", mock_disable),
    ):
        result = await cancel_reminder(ctx, "r1")

    assert result.startswith("Cancelled")
    mock_disable.assert_awaited_once_with(ctx.deps.supabase_client, "r1")


@pytest.mark.asyncio
async def test_cancel_reminder_refuses_system_schedules():
    """cancel_reminder must never touch operator-created jobs like nightly evals."""
    ctx = _make_ctx()
    system_row = ProactiveSchedule.model_validate(
        _schedule_row(source="system", cron="0 3 * * *", run_at=None)
    )
    mock_disable = AsyncMock()
    with (
        patch("jordan_claw.tools.reminders.get_schedule", AsyncMock(return_value=system_row)),
        patch("jordan_claw.tools.reminders.disable_schedule", mock_disable),
    ):
        result = await cancel_reminder(ctx, "r1")

    assert "No reminder with id" in result
    mock_disable.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_reminder_unknown_id():
    ctx = _make_ctx()
    with patch("jordan_claw.tools.reminders.get_schedule", AsyncMock(return_value=None)):
        result = await cancel_reminder(ctx, "nope")
    assert "No reminder with id" in result
