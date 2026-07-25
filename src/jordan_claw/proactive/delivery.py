from __future__ import annotations

import structlog
from supabase._async.client import AsyncClient

from jordan_claw.analytics import emitter
from jordan_claw.db.proactive import (
    insert_proactive_message,
    was_sent_today,
    was_sent_within,
)

log = structlog.get_logger()


async def publish_proactive_message(
    *,
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
    """Persist a proactive artifact for app surfaces and emit analytics."""
    if not content:
        return

    # Dedup: only check scheduled artifacts (those with a schedule_id).
    # Reminders may legitimately recur more than once a day, so they only
    # guard the scheduler's dispatch race window instead of the whole day.
    if schedule_id:
        if task_type == "reminder":
            duplicate = await was_sent_within(db, schedule_id, minutes=5)
        else:
            duplicate = await was_sent_today(db, schedule_id, timezone)
        if duplicate:
            log.info("proactive.dedup_skipped", schedule_id=schedule_id, task_type=task_type)
            return

    await insert_proactive_message(
        db,
        org_id=org_id,
        task_type=task_type,
        trigger=trigger,
        content=content,
        schedule_id=schedule_id,
        channel="app",
    )

    await emitter.proactive_sent(
        org_id=org_id,
        user_id=None,
        schedule_name=schedule_name,
        task_type=task_type,
        channel="app",
        content_length=len(content),
        agent_slug=agent_slug,
        trigger=trigger,
    )

    log.info("proactive.published", org_id=org_id, task_type=task_type, trigger=trigger)
