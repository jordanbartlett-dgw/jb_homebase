from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel
from supabase._async.client import AsyncClient


class EventTrigger(BaseModel):
    """A row from the event_triggers table."""

    id: str
    org_id: str
    source: str
    name: str
    enabled: bool
    agent_slug: str
    prompt_template: str
    filter: dict
    created_at: str


async def get_triggers(client: AsyncClient, source: str) -> list[EventTrigger]:
    """Load enabled event triggers for a source."""
    result = (
        await client.table("event_triggers")
        .select("*")
        .eq("source", source)
        .eq("enabled", True)
        .execute()
    )
    return [EventTrigger.model_validate(row) for row in result.data]


async def get_cursor(client: AsyncClient, source: str) -> dict:
    """Load the watcher cursor for a source. Empty dict when none stored."""
    result = (
        await client.table("watcher_cursors")
        .select("cursor")
        .eq("source", source)
        .limit(1)
        .execute()
    )
    if not result.data:
        return {}
    return result.data[0].get("cursor") or {}


async def save_cursor(client: AsyncClient, source: str, cursor: dict) -> None:
    """Upsert the watcher cursor for a source."""
    await (
        client.table("watcher_cursors")
        .upsert(
            {
                "source": source,
                "cursor": cursor,
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        .execute()
    )
