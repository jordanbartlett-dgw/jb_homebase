from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from croniter import croniter
from pydantic_ai import RunContext

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.db.proactive import (
    disable_schedule,
    get_schedule,
    insert_reminder_schedule,
    list_reminder_schedules,
)
from jordan_claw.proactive.models import ProactiveSchedule

CENTRAL_TZ = ZoneInfo("America/Chicago")
TIME_FMT = "%A %Y-%m-%d %H:%M %Z"


def _next_run(schedule: ProactiveSchedule) -> str:
    tz = ZoneInfo(schedule.timezone)
    if schedule.run_at is not None:
        return schedule.run_at.astimezone(tz).strftime(TIME_FMT)
    cron = croniter(schedule.cron_expression, datetime.now(tz))
    next_time: datetime = cron.get_next(datetime)
    return f"{next_time.strftime(TIME_FMT)} (recurring: {schedule.cron_expression})"


async def set_reminder(
    ctx: RunContext[AgentDeps],
    message: str,
    run_at: datetime | None = None,
    cron: str | None = None,
    agent_slug: str = "claw-main",
) -> str:
    """Create a reminder that gets sent to Jordan over Telegram at the right time.
    Pass exactly one of run_at (absolute datetime, for a one-off reminder) or
    cron (5-field cron expression evaluated in US Central, for a recurring one).
    ALWAYS call current_datetime first and convert relative phrases like
    "in an hour" or "tomorrow morning" to an absolute US Central time yourself.
    NOT for meetings or appointments — use schedule_event to put those on the
    calendar. message is the text Jordan will receive, so write it to him."""
    if (run_at is None) == (cron is None):
        return "Not set: pass exactly one of run_at (one-off) or cron (recurring)."

    now = datetime.now(CENTRAL_TZ)
    if run_at is not None:
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=CENTRAL_TZ)
        if run_at <= now:
            return (
                f"Not set: {run_at.strftime(TIME_FMT)} is in the past. "
                f"It is now {now.strftime(TIME_FMT)}."
            )
    if cron is not None:
        try:
            croniter(cron, now)
        except (ValueError, KeyError):
            return f"Not set: {cron!r} is not a valid 5-field cron expression."

    row = await insert_reminder_schedule(
        ctx.deps.supabase_client,
        ctx.deps.org_id,
        message=message,
        agent_slug=agent_slug,
        run_at=run_at,
        cron=cron,
    )
    schedule = ProactiveSchedule.model_validate(row)
    return f"Reminder set (id {row['id']}). Next: {_next_run(schedule)}."


async def list_reminders(ctx: RunContext[AgentDeps]) -> str:
    """List Jordan's pending reminders with their ids and next run times.
    Only shows reminders he created — never internal system schedules.
    NOT for calendar events — use check_calendar for those."""
    reminders = await list_reminder_schedules(ctx.deps.supabase_client, ctx.deps.org_id)
    if not reminders:
        return "No pending reminders."
    lines = [f"{len(reminders)} pending reminder(s):"]
    for r in reminders:
        message = r.config.get("message", "")
        lines.append(f"- [{r.id}] {message} — next: {_next_run(r)}")
    return "\n".join(lines)


async def cancel_reminder(ctx: RunContext[AgentDeps], reminder_id: str) -> str:
    """Cancel a pending reminder by its id (get ids from list_reminders).
    Only cancels reminders Jordan created — refuses system schedules."""
    schedule = await get_schedule(ctx.deps.supabase_client, reminder_id)
    if schedule is None or schedule.source != "reminder" or schedule.org_id != ctx.deps.org_id:
        return f"No reminder with id {reminder_id}. Use list_reminders to see pending ones."
    if not schedule.enabled:
        return "That reminder is already done or cancelled."
    await disable_schedule(ctx.deps.supabase_client, reminder_id)
    return f"Cancelled: {schedule.config.get('message', reminder_id)}"
