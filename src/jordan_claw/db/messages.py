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


async def get_message_by_channel_id(client: AsyncClient, channel_message_id: str) -> dict | None:
    """Fetch the stored message row for a channel_message_id.

    Same lookup as message_exists, but returns the row so a replayed request
    can converge on the original run (conversation, transcript, routed agent).
    """
    result = (
        await client.table("messages")
        .select("id, conversation_id, role, content, created_at, metadata")
        .eq("channel_message_id", channel_message_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


async def get_assistant_reply_after(
    client: AsyncClient,
    conversation_id: str,
    after: str,
) -> dict | None:
    """First assistant message in a conversation created strictly after `after`.

    Used by the voice replay path to find the reply the original run produced
    for the user message persisted at `after` (ISO timestamp).
    """
    result = (
        await client.table("messages")
        .select("content, created_at, metadata")
        .eq("conversation_id", conversation_id)
        .eq("role", "assistant")
        .gt("created_at", after)
        .order("created_at", desc=False)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


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
        .select("role, content, created_at, token_count, model, metadata, channel_message_id")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return list(reversed(result.data))


async def get_messages_for_conversations(
    client: AsyncClient,
    conversation_ids: list[str],
) -> list[dict]:
    """Fetch user/assistant transcript rows for several conversations at once.

    History pages call this once per page to avoid one messages query per
    conversation.
    """
    if not conversation_ids:
        return []
    result = (
        await client.table("messages")
        .select("id, conversation_id, role, content, created_at")
        .in_("conversation_id", conversation_ids)
        .in_("role", ["user", "assistant"])
        .order("created_at", desc=False)
        .execute()
    )
    return result.data


async def get_conversation_messages(
    client: AsyncClient,
    conversation_id: str,
) -> list[dict]:
    """Fetch the readable user/assistant transcript for one conversation."""
    result = (
        await client.table("messages")
        .select("id, conversation_id, role, content, created_at")
        .eq("conversation_id", conversation_id)
        .in_("role", ["user", "assistant"])
        .order("created_at", desc=False)
        .execute()
    )
    return result.data


async def search_archived_messages(
    client: AsyncClient,
    *,
    org_id: str,
    agent_slug: str,
    query: str,
    window_start: str,
    window_end: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """ILIKE search over one agent's archived app-channel transcripts.

    The !inner join makes the conversation filters restrict message rows;
    without it PostgREST returns messages with a null embed instead of
    filtering them out.
    """
    q = (
        client.table("messages")
        .select(
            "content, role, created_at, conversation_id, "
            "conversations!inner(org_id, channel, channel_thread_id, status, created_at)"
        )
        .eq("conversations.org_id", org_id)
        .eq("conversations.channel", "app")
        .eq("conversations.channel_thread_id", agent_slug)
        .eq("conversations.status", "archived")
        .gte("conversations.created_at", window_start)
        .in_("role", ["user", "assistant"])
        .ilike("content", f"%{query}%")
        .order("created_at", desc=True)
        .limit(limit)
    )
    if window_end is not None:
        q = q.lte("conversations.created_at", window_end)
    result = await q.execute()
    return result.data


async def get_conversation_messages_page(
    client: AsyncClient,
    conversation_id: str,
    *,
    offset: int,
    limit: int,
) -> tuple[list[dict], int]:
    """One oldest-first page of a transcript plus the exact total row count."""
    result = (
        await client.table("messages")
        .select("role, content, created_at", count="exact")
        .eq("conversation_id", conversation_id)
        .in_("role", ["user", "assistant"])
        .order("created_at", desc=False)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return result.data, result.count or 0
