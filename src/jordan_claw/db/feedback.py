from __future__ import annotations

from supabase._async.client import AsyncClient


async def save_feedback(
    client: AsyncClient,
    *,
    org_id: str,
    agent_slug: str,
    conversation_id: str | None,
    rating: int,
    note: str | None,
    prompt_source: str,
) -> None:
    """Insert one row into feedback. None-valued optional fields are dropped."""
    data: dict = {
        "org_id": org_id,
        "agent_slug": agent_slug,
        "rating": rating,
        "prompt_source": prompt_source,
    }
    if conversation_id is not None:
        data["conversation_id"] = conversation_id
    if note is not None:
        data["note"] = note

    await client.table("feedback").insert(data).execute()
