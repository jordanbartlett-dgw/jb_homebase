from __future__ import annotations

from supabase._async.client import AsyncClient


async def get_or_create_conversation(
    client: AsyncClient,
    org_id: str,
    channel: str,
    channel_thread_id: str,
) -> dict:
    """Find an active conversation or create a new one."""
    result = (
        await client.table("conversations")
        .select("*")
        .eq("org_id", org_id)
        .eq("channel", channel)
        .eq("channel_thread_id", channel_thread_id)
        .eq("status", "active")
        .maybe_single()
        .execute()
    )

    if result.data:
        return result.data

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
        client.table("conversations")
        .update({"status": status})
        .eq("id", conversation_id)
        .execute()
    )
