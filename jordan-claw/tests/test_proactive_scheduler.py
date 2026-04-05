from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jordan_claw.proactive.models import ProactiveSchedule


def _make_schedule(
    task_type: str = "morning_briefing",
    cron: str = "0 7 * * *",
    last_run: datetime | None = None,
    schedule_id: str = "s1",
    timezone: str = "America/Chicago",
) -> ProactiveSchedule:
    return ProactiveSchedule(
        id=schedule_id,
        org_id="org-1",
        name=task_type,
        cron_expression=cron,
        timezone=timezone,
        enabled=True,
        task_type=task_type,
        config={"agent_slug": "claw-main"},
        last_run_at=last_run,
        created_at="2026-04-05T00:00:00+00:00",
    )


def test_should_run_never_run_before():
    from jordan_claw.proactive.scheduler import should_run

    schedule = _make_schedule(last_run=None)
    now = datetime(2026, 4, 5, 13, 0, 0, tzinfo=UTC)  # 8am Central (past 7am)
    assert should_run(schedule, now) is True


def test_should_run_already_ran_today():
    from jordan_claw.proactive.scheduler import should_run

    last_run = datetime(2026, 4, 5, 12, 0, 0, tzinfo=UTC)  # 7am Central today
    schedule = _make_schedule(last_run=last_run)
    now = datetime(2026, 4, 5, 14, 0, 0, tzinfo=UTC)  # 9am Central today
    assert should_run(schedule, now) is False


def test_should_run_missed_run_after_restart():
    from jordan_claw.proactive.scheduler import should_run

    last_run = datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC)
    schedule = _make_schedule(last_run=last_run)
    now = datetime(2026, 4, 5, 13, 15, 0, tzinfo=UTC)  # 8:15am Central, past 7am
    assert should_run(schedule, now) is True


def test_should_run_not_yet_time():
    from jordan_claw.proactive.scheduler import should_run

    last_run = datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC)  # yesterday
    schedule = _make_schedule(last_run=last_run)
    now = datetime(2026, 4, 5, 11, 0, 0, tzinfo=UTC)  # 6am Central, before 7am
    assert should_run(schedule, now) is False


def test_should_run_weekly_correct_day():
    from jordan_claw.proactive.scheduler import should_run

    schedule = _make_schedule(task_type="weekly_review", cron="0 8 * * 1", last_run=None)
    # 2026-04-06 is a Monday
    now = datetime(2026, 4, 6, 14, 0, 0, tzinfo=UTC)  # 9am Central Monday
    assert should_run(schedule, now) is True


def test_should_run_weekly_wrong_day():
    from jordan_claw.proactive.scheduler import should_run

    schedule = _make_schedule(task_type="weekly_review", cron="0 8 * * 1", last_run=None)
    # 2026-04-05 is a Saturday
    now = datetime(2026, 4, 5, 14, 0, 0, tzinfo=UTC)
    assert should_run(schedule, now) is False


@pytest.mark.asyncio
async def test_dispatch_task_calls_executor():
    from jordan_claw.proactive.scheduler import dispatch_task

    schedule = _make_schedule(task_type="morning_briefing")
    mock_db = AsyncMock()
    mock_bot = AsyncMock()
    mock_settings = MagicMock()

    mock_exec = AsyncMock(return_value="Good morning!")
    mock_send = AsyncMock()

    with (
        patch(
            "jordan_claw.proactive.scheduler.EXECUTOR_MAP",
            {"morning_briefing": mock_exec},
        ),
        patch(
            "jordan_claw.proactive.scheduler.send_proactive_message",
            new=mock_send,
        ),
        patch(
            "jordan_claw.proactive.scheduler.update_last_run",
            new=AsyncMock(),
        ),
    ):
        await dispatch_task(schedule, mock_db, mock_bot, mock_settings)

    mock_exec.assert_called_once()
    mock_send.assert_called_once()
