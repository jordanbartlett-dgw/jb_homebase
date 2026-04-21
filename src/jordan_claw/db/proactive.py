from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import structlog
from supabase._async.client import AsyncClient

from jordan_claw.proactive.models import ProactiveSchedule

log = structlog.get_logger()


async def get_enabled_schedules(client: AsyncClient) -> list[ProactiveSchedule]:
    """Load all enabled proactive schedules."""
    result = (
        await client.table("proactive_schedules")
        .select("*")
        .eq("enabled", True)
        .execute()
    )
    return [ProactiveSchedule.model_validate(row) for row in result.data]


async def update_last_run(client: AsyncClient, schedule_id: str) -> None:
    """Update last_run_at to now for a schedule."""
    await (
        client.table("proactive_schedules")
        .update({"last_run_at": datetime.now(UTC).isoformat()})
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
    channel: str = "telegram",
) -> None:
    """Insert an audit row for a sent proactive message."""
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


async def get_telegram_chat_id(
    client: AsyncClient,
    org_id: str,
) -> int | None:
    """Look up the Telegram chat ID for an org."""
    result = (
        await client.table("organizations")
        .select("telegram_chat_id")
        .eq("id", org_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return result.data[0].get("telegram_chat_id")


async def save_telegram_chat_id(
    client: AsyncClient,
    org_id: str,
    chat_id: int,
) -> None:
    """Persist the Telegram chat ID on the org record."""
    await (
        client.table("organizations")
        .update({"telegram_chat_id": chat_id})
        .eq("id", org_id)
        .execute()
    )
