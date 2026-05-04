from __future__ import annotations

import structlog
from aiogram import Bot
from supabase._async.client import AsyncClient

from jordan_claw.analytics import emitter
from jordan_claw.db.proactive import (
    get_telegram_chat_id,
    insert_proactive_message,
    was_sent_today,
)

log = structlog.get_logger()


async def send_proactive_message(
    *,
    bot: Bot,
    db: AsyncClient,
    org_id: str,
    content: str,
    task_type: str,
    trigger: str,
    schedule_id: str | None = None,
    schedule_name: str | None = None,
    agent_slug: str | None = None,
    timezone: str = "America/Chicago",
) -> None:
    """Send a proactive message via Telegram and log it."""
    if not content:
        return

    chat_id = await get_telegram_chat_id(db, org_id)
    if chat_id is None:
        log.warning("proactive.no_chat_id", org_id=org_id, task_type=task_type)
        return

    # Dedup: only check for scheduled messages (those with a schedule_id)
    if schedule_id and await was_sent_today(db, schedule_id, timezone):
        log.info(
            "proactive.dedup_skipped", schedule_id=schedule_id, task_type=task_type
        )
        return

    try:
        await bot.send_message(chat_id, content)
    except Exception:
        log.exception("proactive.send_failed", org_id=org_id, task_type=task_type)
        return

    await insert_proactive_message(
        db,
        org_id=org_id,
        task_type=task_type,
        trigger=trigger,
        content=content,
        schedule_id=schedule_id,
    )

    await emitter.proactive_sent(
        org_id=org_id,
        user_id=None,
        schedule_name=schedule_name,
        task_type=task_type,
        channel="telegram",
        content_length=len(content),
        agent_slug=agent_slug,
        trigger=trigger,
    )

    log.info("proactive.sent", org_id=org_id, task_type=task_type, trigger=trigger)
