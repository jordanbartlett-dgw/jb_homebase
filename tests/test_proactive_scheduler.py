from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from jordan_claw.proactive.models import ProactiveSchedule


def _make_schedule(
    task_type: str = "morning_briefing",
    cron: str | None = "0 7 * * *",
    last_run: datetime | None = None,
    schedule_id: str = "s1",
    timezone: str = "America/Chicago",
    config: dict | None = None,
    run_at: datetime | None = None,
    source: str = "system",
) -> ProactiveSchedule:
    return ProactiveSchedule(
        id=schedule_id,
        org_id="org-1",
        name=task_type,
        cron_expression=cron,
        run_at=run_at,
        timezone=timezone,
        enabled=True,
        task_type=task_type,
        config=config or {"agent_slug": "claw-main"},
        source=source,
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


def test_should_run_one_shot_due():
    from jordan_claw.proactive.scheduler import should_run

    run_at = datetime(2026, 7, 25, 15, 0, 0, tzinfo=UTC)
    schedule = _make_schedule(task_type="reminder", cron=None, run_at=run_at, source="reminder")
    assert should_run(schedule, datetime(2026, 7, 25, 15, 1, 0, tzinfo=UTC)) is True


def test_should_run_one_shot_not_yet_due():
    from jordan_claw.proactive.scheduler import should_run

    run_at = datetime(2026, 7, 25, 15, 0, 0, tzinfo=UTC)
    schedule = _make_schedule(task_type="reminder", cron=None, run_at=run_at, source="reminder")
    assert should_run(schedule, datetime(2026, 7, 25, 14, 59, 0, tzinfo=UTC)) is False


def test_should_run_one_shot_never_refires():
    from jordan_claw.proactive.scheduler import should_run

    run_at = datetime(2026, 7, 25, 15, 0, 0, tzinfo=UTC)
    schedule = _make_schedule(
        task_type="reminder",
        cron=None,
        run_at=run_at,
        source="reminder",
        last_run=datetime(2026, 7, 25, 15, 1, 0, tzinfo=UTC),
    )
    assert should_run(schedule, datetime(2026, 7, 25, 18, 0, 0, tzinfo=UTC)) is False


def test_should_run_false_when_neither_cron_nor_run_at():
    from jordan_claw.proactive.scheduler import should_run

    schedule = _make_schedule(cron=None, run_at=None)
    assert should_run(schedule, datetime(2026, 7, 25, 15, 0, 0, tzinfo=UTC)) is False


@pytest.mark.asyncio
async def test_dispatch_one_shot_disables_schedule():
    from jordan_claw.proactive.scheduler import dispatch_task

    schedule = _make_schedule(
        task_type="reminder",
        cron=None,
        run_at=datetime(2026, 7, 25, 15, 0, 0, tzinfo=UTC),
        source="reminder",
        config={"agent_slug": "claw-main", "message": "Call the accountant"},
    )
    settings = MagicMock(default_agent_slug="claw-main")
    mock_disable = AsyncMock()

    with (
        patch.dict(
            "jordan_claw.proactive.scheduler.EXECUTOR_MAP",
            {"reminder": AsyncMock(return_value="Call the accountant")},
        ),
        patch("jordan_claw.proactive.scheduler.publish_proactive_message"),
        patch("jordan_claw.proactive.scheduler.update_last_run", new=AsyncMock()),
        patch("jordan_claw.proactive.scheduler.disable_schedule", new=mock_disable),
    ):
        await dispatch_task(schedule, MagicMock(), settings)

    mock_disable.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_cron_schedule_stays_enabled():
    from jordan_claw.proactive.scheduler import dispatch_task

    schedule = _make_schedule(task_type="reminder", cron="0 9 * * *", source="reminder")
    settings = MagicMock(default_agent_slug="claw-main")
    mock_disable = AsyncMock()

    with (
        patch.dict(
            "jordan_claw.proactive.scheduler.EXECUTOR_MAP",
            {"reminder": AsyncMock(return_value="Drink water")},
        ),
        patch("jordan_claw.proactive.scheduler.publish_proactive_message"),
        patch("jordan_claw.proactive.scheduler.update_last_run", new=AsyncMock()),
        patch("jordan_claw.proactive.scheduler.disable_schedule", new=mock_disable),
    ):
        await dispatch_task(schedule, MagicMock(), settings)

    mock_disable.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_task_calls_executor():
    from jordan_claw.proactive.scheduler import dispatch_task

    schedule = _make_schedule(task_type="morning_briefing")
    mock_db = AsyncMock()
    mock_settings = MagicMock(default_agent_slug="claw-main")

    mock_exec = AsyncMock(return_value="Good morning!")
    mock_send = AsyncMock()

    with (
        patch(
            "jordan_claw.proactive.scheduler.EXECUTOR_MAP",
            {"morning_briefing": mock_exec},
        ),
        patch(
            "jordan_claw.proactive.scheduler.publish_proactive_message",
            new=mock_send,
        ),
        patch(
            "jordan_claw.proactive.scheduler.update_last_run",
            new=AsyncMock(),
        ),
    ):
        await dispatch_task(schedule, mock_db, mock_settings)

    mock_exec.assert_called_once()
    mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_dispatch_publishes_agent_slug():
    from jordan_claw.proactive.scheduler import dispatch_task

    schedule = _make_schedule(task_type="daily_workout", config={"agent_slug": "workout-coach"})
    settings = MagicMock(default_agent_slug="claw-main")

    with (
        patch.dict(
            "jordan_claw.proactive.scheduler.EXECUTOR_MAP",
            {"daily_workout": AsyncMock(return_value="go run")},
        ),
        patch("jordan_claw.proactive.scheduler.publish_proactive_message") as mock_publish,
        patch("jordan_claw.proactive.scheduler.update_last_run"),
    ):
        await dispatch_task(schedule, MagicMock(), settings)

    assert mock_publish.call_args.kwargs["agent_slug"] == "workout-coach"


@pytest.mark.asyncio
async def test_schedule_calendar_reminders_sets_timers():
    from datetime import timedelta

    from jordan_claw.proactive.scheduler import schedule_calendar_reminders

    mock_db = AsyncMock()
    mock_settings = MagicMock()
    mock_settings.fastmail_username = "user@test.com"
    mock_settings.fastmail_app_password = "test-pass"

    tz = ZoneInfo("America/Chicago")
    now = datetime.now(tz)
    future_start = now + timedelta(hours=2)
    future_end = future_start + timedelta(hours=1)

    events_text = (
        f"- Big meeting: {future_start.strftime('%H:%M')} - {future_end.strftime('%H:%M')}"
    )

    with (
        patch(
            "jordan_claw.proactive.scheduler.get_calendar_events",
            new=AsyncMock(return_value=events_text),
        ),
        patch(
            "jordan_claw.proactive.scheduler._parse_event_times",
            return_value=[("Big meeting", future_start, future_end)],
        ),
    ):
        timers = await schedule_calendar_reminders(
            mock_db,
            "org-1",
            {"agent_slug": "claw-main"},
            mock_settings,
        )

    assert len(timers) == 1
