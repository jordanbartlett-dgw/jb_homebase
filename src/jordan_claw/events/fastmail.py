from __future__ import annotations

import httpx
import structlog
from supabase._async.client import AsyncClient

from jordan_claw.config import Settings
from jordan_claw.db.event_triggers import get_cursor, save_cursor
from jordan_claw.events.pipeline import process_event

log = structlog.get_logger()

JMAP_SESSION_URL = "https://api.fastmail.com/jmap/session"
JMAP_CORE = "urn:ietf:params:jmap:core"
JMAP_MAIL = "urn:ietf:params:jmap:mail"
SOURCE = "fastmail-email"
POLL_LIMIT = 20

_no_token_logged = False


def _format_from(addresses: list[dict] | None) -> str:
    if not addresses:
        return "(unknown sender)"
    first = addresses[0]
    name = first.get("name")
    email = first.get("email", "")
    return f"{name} <{email}>" if name else email


def _to_payload(email: dict) -> dict:
    return {
        "from": _format_from(email.get("from")),
        "subject": email.get("subject") or "(no subject)",
        "snippet": email.get("preview") or "",
    }


async def _fetch_emails(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    after: str | None,
) -> list[dict]:
    """Query Fastmail JMAP for recent emails, returned oldest first."""
    session_resp = await client.get(JMAP_SESSION_URL, headers=headers)
    session_resp.raise_for_status()
    session = session_resp.json()
    api_url = session["apiUrl"]
    account_id = session["primaryAccounts"][JMAP_MAIL]

    first_poll = after is None
    query_args: dict = {
        "accountId": account_id,
        # Cursor-filtered polls sort ascending so a >POLL_LIMIT burst
        # truncates to the OLDEST emails; the cursor then parks at the newest
        # processed one and the remainder arrives next poll (no loss).
        # The first poll sorts descending: it only wants the newest email
        # as the cursor seed.
        "sort": [{"property": "receivedAt", "isAscending": not first_poll}],
        "limit": 1 if first_poll else POLL_LIMIT,
    }
    if not first_poll:
        query_args["filter"] = {"after": after}

    body = {
        "using": [JMAP_CORE, JMAP_MAIL],
        "methodCalls": [
            ["Email/query", query_args, "0"],
            [
                "Email/get",
                {
                    "accountId": account_id,
                    "#ids": {"resultOf": "0", "name": "Email/query", "path": "/ids"},
                    "properties": ["id", "receivedAt", "from", "subject", "preview"],
                },
                "1",
            ],
        ],
    }
    resp = await client.post(api_url, headers=headers, json=body)
    resp.raise_for_status()

    emails: list[dict] = []
    for name, args, _call_id in resp.json().get("methodResponses", []):
        if name == "Email/get":
            emails = args.get("list", [])
    # Email/get list order isn't guaranteed by RFC 8620; normalize oldest first.
    return sorted(emails, key=lambda e: e["receivedAt"])


async def poll_fastmail(
    db: AsyncClient,
    settings: Settings,
) -> int:
    """Poll Fastmail via JMAP and fire process_event per new email.

    Returns the number of emails processed. First poll seeds the cursor
    from the newest email without firing anything (no backfill storm).
    """
    global _no_token_logged
    if not settings.fastmail_api_token:
        if not _no_token_logged:
            log.info("fastmail.watcher_disabled_no_token")
            _no_token_logged = True
        return 0

    cursor = await get_cursor(db, SOURCE)
    after = cursor.get("after")

    headers = {"Authorization": f"Bearer {settings.fastmail_api_token}"}
    async with httpx.AsyncClient(timeout=30) as client:
        emails = await _fetch_emails(client, headers, after)

    if after is None:
        if emails:
            newest = emails[-1]
            await save_cursor(db, SOURCE, {"after": newest["receivedAt"], "last_id": newest["id"]})
        log.info("fastmail.cursor_initialized", seeded=bool(emails))
        return 0

    # JMAP "after" is inclusive (receivedAt on-or-after), so the cursor
    # email echoes back: drop it by id; the >= filter keeps at-or-newer rows.
    last_id = cursor.get("last_id")
    new_emails = [e for e in emails if e["id"] != last_id and e["receivedAt"] >= after]

    processed = 0
    for email in new_emails:  # already oldest first
        await process_event(
            db,
            source=SOURCE,
            payload=_to_payload(email),
            settings=settings,
        )
        processed += 1

    if new_emails:
        # Park the cursor at the newest email we actually processed; any
        # overflow past POLL_LIMIT is picked up by the next poll.
        newest = new_emails[-1]
        await save_cursor(db, SOURCE, {"after": newest["receivedAt"], "last_id": newest["id"]})

    log.info("fastmail.poll_complete", processed=processed)
    return processed
