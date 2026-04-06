from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from supabase._async.client import AsyncClient

log = structlog.get_logger()

SESSION_TIMEOUT_MINUTES = 30


async def _last_message_time(client: AsyncClient, conversation_id: str) -> datetime | None:
    """Get the timestamp of the most recent message in a conversation."""
    result = (
        await client.table("messages")
        .select("created_at")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return datetime.fromisoformat(result.data[0]["created_at"])


async def get_or_create_conversation(
    client: AsyncClient,
    org_id: str,
    channel: str,
    channel_thread_id: str,
) -> dict:
    """Find an active conversation or create a new one.

    Closes conversations that have been idle longer than SESSION_TIMEOUT_MINUTES
    and starts a fresh one, so unrelated topics don't bleed into context.
    """
    result = (
        await client.table("conversations")
        .select("*")
        .eq("org_id", org_id)
        .eq("channel", channel)
        .eq("channel_thread_id", channel_thread_id)
        .eq("status", "active")
        .limit(1)
        .execute()
    )

    if result.data:
        conversation = result.data[0]
        last_msg = await _last_message_time(client, conversation["id"])

        if last_msg and (datetime.now(UTC) - last_msg) > timedelta(minutes=SESSION_TIMEOUT_MINUTES):
            log.info(
                "conversation_session_expired",
                conversation_id=conversation["id"],
                idle_minutes=int((datetime.now(UTC) - last_msg).total_seconds() / 60),
            )
            await client.table("conversations").update({"status": "archived"}).eq(
                "id", conversation["id"]
            ).execute()
        else:
            return conversation

    result = (
        await client.table("conversations")
        .insert(
            {
                "org_id": org_id,
                "channel": channel,
                "channel_thread_id": channel_thread_id,
            }
        )
        .execute()
    )
    return result.data[0]


async def update_conversation_status(
    client: AsyncClient,
    conversation_id: str,
    status: str,
) -> None:
    """Update a conversation's status."""
    await (
        client.table("conversations").update({"status": status}).eq("id", conversation_id).execute()
    )
