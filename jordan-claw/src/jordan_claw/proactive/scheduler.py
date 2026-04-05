from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import structlog
from aiogram import Bot
from croniter import croniter
from supabase._async.client import AsyncClient

from jordan_claw.config import Settings
from jordan_claw.db.proactive import get_enabled_schedules, update_last_run
from jordan_claw.proactive.delivery import send_proactive_message
from jordan_claw.proactive.executors import (
    _parse_event_times,
    execute_calendar_reminder,
    execute_daily_scan,
    execute_morning_briefing,
    execute_weekly_review,
)
from jordan_claw.proactive.models import ProactiveSchedule
from jordan_claw.tools.calendar import get_calendar_events

log = structlog.get_logger()

EXECUTOR_MAP = {
    "morning_briefing": execute_morning_briefing,
    "weekly_review": execute_weekly_review,
    "daily_scan": execute_daily_scan,
}

CHECK_INTERVAL_SECONDS = 60


def should_run(schedule: ProactiveSchedule, now: datetime) -> bool:
    """Determine if a schedule should fire based on its cron expression and last run."""
    tz = ZoneInfo(schedule.timezone)
    now_local = now.astimezone(tz)

    if schedule.last_run_at is None:
        # Never run before: check if we're past the most recent cron time
        cron = croniter(schedule.cron_expression, now_local - timedelta(days=1))
        next_time = cron.get_next(datetime)
        return next_time <= now_local
    else:
        last_run_local = schedule.last_run_at.astimezone(tz)
        cron = croniter(schedule.cron_expression, last_run_local)
        next_time = cron.get_next(datetime)
        return next_time <= now_local


async def dispatch_task(
    schedule: ProactiveSchedule,
    db: AsyncClient,
    bot: Bot,
    settings: Settings,
) -> None:
    """Execute a scheduled task and send the result."""
    executor = EXECUTOR_MAP.get(schedule.task_type)
    if not executor:
        log.warning("proactive.unknown_task_type", task_type=schedule.task_type)
        return

    try:
        content = await executor(db, schedule.org_id, schedule.config, settings)

        await send_proactive_message(
            bot=bot,
            db=db,
            org_id=schedule.org_id,
            content=content,
            task_type=schedule.task_type,
            trigger="scheduled",
            schedule_id=schedule.id,
            timezone=schedule.timezone,
        )

        await update_last_run(db, schedule.id)

        # After morning briefing, schedule calendar reminders for today
        if schedule.task_type == "morning_briefing":
            await schedule_calendar_reminders(
                db, schedule.org_id, schedule.config, settings, bot,
            )

        log.info(
            "proactive.task_complete",
            task_type=schedule.task_type,
            schedule_id=schedule.id,
            had_content=bool(content),
        )
    except Exception:
        log.exception(
            "proactive.task_failed",
            task_type=schedule.task_type,
            schedule_id=schedule.id,
        )


async def schedule_calendar_reminders(
    db: AsyncClient,
    org_id: str,
    config: dict,
    settings: Settings,
    bot: Bot,
) -> list[asyncio.TimerHandle]:
    """Scan today's events and set 30-min-before reminder timers."""
    tz = ZoneInfo("America/Chicago")
    now = datetime.now(tz)
    today_str = now.strftime("%Y-%m-%d")

    events_text = await get_calendar_events(
        settings.fastmail_username, settings.fastmail_app_password,
        today_str, today_str,
    )

    if events_text == "No events scheduled.":
        return []

    events = _parse_event_times(events_text)
    timers: list[asyncio.TimerHandle] = []
    loop = asyncio.get_running_loop()

    for title, start, _end in events:
        remind_at = start - timedelta(minutes=30)
        delay = (remind_at - now).total_seconds()

        if delay <= 0:
            continue

        async def _fire_reminder(t: str = title, s: str = start.strftime("%H:%M")) -> None:
            try:
                content = await execute_calendar_reminder(
                    db, org_id, config, settings,
                    event_title=t, event_time=s,
                )
                await send_proactive_message(
                    bot=bot,
                    db=db,
                    org_id=org_id,
                    content=content,
                    task_type="calendar_reminder",
                    trigger="calendar_reminder",
                )
            except Exception:
                log.exception("proactive.calendar_reminder_failed", event_title=t)

        handle = loop.call_later(delay, lambda coro=_fire_reminder: asyncio.create_task(coro()))
        timers.append(handle)
        log.info("proactive.reminder_scheduled", event_title=title, delay_seconds=int(delay))

    return timers


async def scheduler_loop(
    db: AsyncClient,
    bot: Bot,
    settings: Settings,
) -> None:
    """Main scheduler loop. Runs every 60 seconds, checking for due schedules."""
    log.info("proactive.scheduler_started")

    while True:
        try:
            schedules = await get_enabled_schedules(db)
            now = datetime.now(UTC)

            for schedule in schedules:
                if should_run(schedule, now):
                    asyncio.create_task(
                        dispatch_task(schedule, db, bot, settings),
                        name=f"proactive-{schedule.task_type}-{schedule.id}",
                    )
        except Exception:
            log.exception("proactive.scheduler_tick_failed")

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
