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
    execute_daily_scan,
    execute_morning_briefing,
    execute_weekly_review,
)
from jordan_claw.proactive.models import ProactiveSchedule

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
