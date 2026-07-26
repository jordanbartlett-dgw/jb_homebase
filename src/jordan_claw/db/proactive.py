from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import structlog
from supabase._async.client import AsyncClient

from jordan_claw.proactive.models import ProactiveSchedule

log = structlog.get_logger()


async def get_enabled_schedules(client: AsyncClient) -> list[ProactiveSchedule]:
    """Load all enabled proactive schedules."""
    result = await client.table("proactive_schedules").select("*").eq("enabled", True).execute()
    return [ProactiveSchedule.model_validate(row) for row in result.data]


async def update_last_run(client: AsyncClient, schedule_id: str) -> None:
    """Update last_run_at to now for a schedule."""
    await (
        client.table("proactive_schedules")
        .update({"last_run_at": datetime.now(UTC).isoformat()})
        .eq("id", schedule_id)
        .execute()
    )


async def insert_reminder_schedule(
    client: AsyncClient,
    org_id: str,
    *,
    message: str,
    agent_slug: str,
    run_at: datetime | None = None,
    cron: str | None = None,
    timezone: str = "America/Chicago",
) -> dict:
    """Insert a reminder schedule row (source='reminder'). Exactly one of
    run_at/cron must be set — callers validate; the DB CHECK backstops."""
    result = await (
        client.table("proactive_schedules")
        .insert(
            {
                "org_id": org_id,
                "name": f"reminder-{uuid4().hex[:12]}",
                "cron_expression": cron,
                "run_at": run_at.isoformat() if run_at else None,
                "timezone": timezone,
                "task_type": "reminder",
                "source": "reminder",
                "config": {"message": message, "agent_slug": agent_slug},
            }
        )
        .execute()
    )
    return result.data[0]


async def list_reminder_schedules(client: AsyncClient, org_id: str) -> list[ProactiveSchedule]:
    """Pending reminder rows only — source='reminder' keeps system jobs
    (evals, briefings, watchers) out of what list_reminders shows Jordan."""
    result = await (
        client.table("proactive_schedules")
        .select("*")
        .eq("org_id", org_id)
        .eq("source", "reminder")
        .eq("enabled", True)
        .order("created_at")
        .execute()
    )
    return [ProactiveSchedule.model_validate(row) for row in result.data]


async def get_schedule(client: AsyncClient, schedule_id: str) -> ProactiveSchedule | None:
    """Fetch one schedule row by id, or None."""
    result = (
        await client.table("proactive_schedules")
        .select("*")
        .eq("id", schedule_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return ProactiveSchedule.model_validate(result.data[0])


async def disable_schedule(client: AsyncClient, schedule_id: str) -> None:
    """Disable a schedule (one-shot completion and reminder cancellation both
    land here — rows are kept because proactive_messages FKs them)."""
    await (
        client.table("proactive_schedules")
        .update({"enabled": False})
        .eq("id", schedule_id)
        .execute()
    )


async def insert_proactive_message(
    client: AsyncClient,
    *,
    org_id: str,
    task_type: str,
    trigger: str,
    content: str,
    schedule_id: str | None = None,
    channel: str = "app",
) -> None:
    """Insert a proactive artifact for an app surface."""
    await (
        client.table("proactive_messages")
        .insert(
            {
                "org_id": org_id,
                "schedule_id": schedule_id,
                "task_type": task_type,
                "trigger": trigger,
                "content": content,
                "channel": channel,
            }
        )
        .execute()
    )


async def get_latest_proactive_message(
    client: AsyncClient,
    *,
    org_id: str,
    task_type: str,
    delivered_from: datetime,
    delivered_before: datetime,
) -> dict | None:
    """Return the latest proactive artifact delivered in a time window."""
    result = (
        await client.table("proactive_messages")
        .select("id, task_type, content, delivered_at")
        .eq("org_id", org_id)
        .eq("task_type", task_type)
        .gte("delivered_at", delivered_from.isoformat())
        .lt("delivered_at", delivered_before.isoformat())
        .order("delivered_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


async def get_recent_proactive_artifacts(
    client: AsyncClient,
    *,
    org_id: str,
    exclude_task_type: str,
    since: datetime,
    limit: int,
) -> list[dict]:
    """Recent proactive artifacts for the app's Today feed: every task_type
    except exclude_task_type (morning_briefing already has its own digest
    slot), delivered since the cutoff, newest first, capped at limit."""
    result = (
        await client.table("proactive_messages")
        .select("task_type, content, delivered_at")
        .eq("org_id", org_id)
        .neq("task_type", exclude_task_type)
        .gte("delivered_at", since.isoformat())
        .order("delivered_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data


async def was_sent_today(
    client: AsyncClient,
    schedule_id: str,
    timezone: str,
) -> bool:
    """Check if a scheduled message was already sent today (in the schedule's timezone)."""
    tz = ZoneInfo(timezone)
    today_start = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_utc = today_start.astimezone(UTC).isoformat()

    result = (
        await client.table("proactive_messages")
        .select("id")
        .eq("schedule_id", schedule_id)
        .gte("delivered_at", today_start_utc)
        .limit(1)
        .execute()
    )
    return len(result.data) > 0


async def was_sent_within(client: AsyncClient, schedule_id: str, *, minutes: int) -> bool:
    """Check if a scheduled message was sent in the last N minutes.

    Reminder dedup: was_sent_today would block sub-daily recurring reminders,
    so reminders only guard the scheduler's >60s dispatch race window."""
    cutoff = (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat()
    result = (
        await client.table("proactive_messages")
        .select("id")
        .eq("schedule_id", schedule_id)
        .gte("delivered_at", cutoff)
        .limit(1)
        .execute()
    )
    return len(result.data) > 0
