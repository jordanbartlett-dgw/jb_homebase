from __future__ import annotations

from supabase._async.client import AsyncClient


async def message_exists(client: AsyncClient, channel_message_id: str) -> bool:
    """Check if a message with this channel_message_id already exists (dedup)."""
    result = (
        await client.table("messages")
        .select("id")
        .eq("channel_message_id", channel_message_id)
        .limit(1)
        .execute()
    )
    return len(result.data) > 0


async def save_message(
    client: AsyncClient,
    conversation_id: str,
    role: str,
    content: str,
    channel_message_id: str | None = None,
    token_count: int | None = None,
    model: str | None = None,
    cost_usd: float | None = None,
    metadata: dict | None = None,
) -> dict:
    """Save a message to the messages table."""
    data: dict = {
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
    }
    if channel_message_id is not None:
        data["channel_message_id"] = channel_message_id
    if token_count is not None:
        data["token_count"] = token_count
    if model is not None:
        data["model"] = model
    if cost_usd is not None:
        data["cost_usd"] = float(cost_usd)
    if metadata is not None:
        data["metadata"] = metadata

    result = await client.table("messages").insert(data).execute()
    return result.data[0]


async def get_recent_messages(
    client: AsyncClient,
    conversation_id: str,
    limit: int = 50,
) -> list[dict]:
    """Get the most recent messages for a conversation, ordered oldest first."""
    result = (
        await client.table("messages")
        .select("role, content, created_at, token_count, model, metadata")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=False)
        .limit(limit)
        .execute()
    )
    return result.data
