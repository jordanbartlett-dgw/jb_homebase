from __future__ import annotations

from datetime import datetime

import logfire
import structlog
from supabase._async.client import AsyncClient

from jordan_claw.config import Settings
from jordan_claw.db.event_triggers import get_cursor, save_cursor
from jordan_claw.events.pipeline import process_event
from jordan_claw.tools.email import get_agentmail_client

log = structlog.get_logger()

SOURCE = "agentmail-email"
POLL_LIMIT = 20

_no_key_logged = False


def _to_payload(item: object) -> dict:
    return {
        "from": getattr(item, "from_", "") or "(unknown sender)",
        "subject": getattr(item, "subject", None) or "(no subject)",
        "snippet": getattr(item, "preview", None) or "",
    }


async def poll_agentmail(db: AsyncClient, settings: Settings) -> int:
    """Poll the agent's AgentMail inbox and fire process_event per new email.

    Returns the number of messages processed. First poll seeds the cursor
    from the newest inbound message without firing anything (no backfill
    storm). Outbound ("sent") messages are never processed.
    """
    global _no_key_logged
    if not settings.agentmail_api_key:
        if not _no_key_logged:
            log.info("agentmail.watcher_disabled_no_key")
            _no_key_logged = True
        return 0

    with logfire.span("agentmail.poll") as span:
        cursor = await get_cursor(db, SOURCE)
        after = cursor.get("after")

        client = get_agentmail_client(settings.agentmail_api_key)

        if after is None:
            # First poll only wants the newest inbound message as the cursor
            # seed. Newest first, limit 1: keep the no-backfill property.
            page = await client.inboxes.messages.list(
                inbox_id=settings.agentmail_inbox_id,
                labels=["received"],
                limit=1,
            )
            inbound = list(getattr(page, "messages", None) or [])
            if inbound:
                newest = inbound[0]
                await save_cursor(
                    db,
                    SOURCE,
                    {"after": newest.timestamp.isoformat(), "last_id": newest.message_id},
                )
            log.info("agentmail.cursor_initialized", seeded=bool(inbound))
            span.set_attribute("processed", 0)
            return 0

        # Cursor-filtered polls fetch server-side ascending (oldest first) so a
        # >POLL_LIMIT burst truncates to the OLDEST messages; the cursor then
        # parks at the newest PROCESSED one and the remainder arrives next poll
        # (no loss). Same no-loss semantics as the fastmail watcher
        # (events/fastmail.py), just with the AgentMail SDK's own after/ascending
        # params instead of a JMAP filter.
        after_dt = datetime.fromisoformat(after)
        page = await client.inboxes.messages.list(
            inbox_id=settings.agentmail_inbox_id,
            labels=["received"],
            after=after_dt,
            ascending=True,
            limit=POLL_LIMIT,
        )
        inbound = list(getattr(page, "messages", None) or [])

        # The listing window overlaps the cursor: keep at-or-after rows, drop the
        # cursor message itself by id (same pattern as the fastmail watcher).
        last_id = cursor.get("last_id")
        new_items = [m for m in inbound if m.message_id != last_id and m.timestamp >= after_dt]

        processed = 0
        for item in new_items:  # already oldest first (ascending=True)
            await process_event(db, source=SOURCE, payload=_to_payload(item), settings=settings)
            processed += 1

        if new_items:
            newest = new_items[-1]
            await save_cursor(
                db,
                SOURCE,
                {"after": newest.timestamp.isoformat(), "last_id": newest.message_id},
            )

        span.set_attribute("processed", processed)
        log.info("agentmail.poll_complete", processed=processed)
        return processed
