from __future__ import annotations

from datetime import UTC, datetime

import structlog
from supabase._async.client import AsyncClient

from jordan_claw.memory.models import ExtractedEvent, ExtractedFact, MemoryFact

log = structlog.get_logger()

CONFIDENCE_THRESHOLD = 0.7


async def get_active_facts(client: AsyncClient, org_id: str) -> list[MemoryFact]:
    """Load all non-archived facts for an org."""
    result = (
        await client.table("memory_facts")
        .select("*")
        .eq("org_id", org_id)
        .eq("is_archived", False)
        .order("confidence", desc=True)
        .order("updated_at", desc=True)
        .execute()
    )
    return [MemoryFact.model_validate(row) for row in result.data]


async def upsert_facts(
    client: AsyncClient,
    org_id: str,
    facts: list[ExtractedFact],
    existing: list[MemoryFact],
) -> None:
    """Insert new facts or handle conflicts with existing ones."""
    existing_by_id = {f.id: f for f in existing}

    for fact in facts:
        if fact.replaces_fact_id and fact.replaces_fact_id in existing_by_id:
            old = existing_by_id[fact.replaces_fact_id]

            if old.confidence < CONFIDENCE_THRESHOLD:
                # Auto-replace: update existing row
                await (
                    client.table("memory_facts")
                    .update(
                        {
                            "content": fact.content,
                            "category": fact.category,
                            "source": fact.source,
                            "confidence": fact.confidence,
                            "updated_at": datetime.now(UTC).isoformat(),
                        }
                    )
                    .eq("id", fact.replaces_fact_id)
                    .execute()
                )
                log.info(
                    "memory_fact_replaced",
                    old_fact_id=fact.replaces_fact_id,
                    new_content=fact.content,
                )
            else:
                # Flag for review: insert new with needs_review
                await (
                    client.table("memory_facts")
                    .insert(
                        {
                            "org_id": org_id,
                            "category": fact.category,
                            "content": fact.content,
                            "source": fact.source,
                            "confidence": fact.confidence,
                            "metadata": {
                                "needs_review": True,
                                "conflicts_with": fact.replaces_fact_id,
                            },
                        }
                    )
                    .execute()
                )
                log.info(
                    "memory_fact_flagged",
                    conflicting_fact_id=fact.replaces_fact_id,
                    new_content=fact.content,
                )
        else:
            # New fact, insert
            await (
                client.table("memory_facts")
                .insert(
                    {
                        "org_id": org_id,
                        "category": fact.category,
                        "content": fact.content,
                        "source": fact.source,
                        "confidence": fact.confidence,
                        "metadata": {},
                    }
                )
                .execute()
            )


async def append_events(
    client: AsyncClient,
    org_id: str,
    events: list[ExtractedEvent],
) -> None:
    """Append memory events."""
    if not events:
        return
    rows = [
        {
            "org_id": org_id,
            "event_type": e.event_type,
            "summary": e.summary,
            "context": {},
        }
        for e in events
    ]
    await client.table("memory_events").insert(rows).execute()


async def get_memory_context(
    client: AsyncClient,
    org_id: str,
    scope: str = "global",
) -> dict | None:
    """Load the pre-rendered context block for an org+scope."""
    result = (
        await client.table("memory_context")
        .select("*")
        .eq("org_id", org_id)
        .eq("scope", scope)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


async def upsert_memory_context(
    client: AsyncClient,
    org_id: str,
    scope: str,
    context_block: str,
) -> None:
    """Upsert the pre-rendered context block."""
    await (
        client.table("memory_context")
        .upsert(
            {
                "org_id": org_id,
                "scope": scope,
                "context_block": context_block,
                "is_stale": False,
                "last_computed": datetime.now(UTC).isoformat(),
            },
        )
        .execute()
    )


async def mark_context_stale(client: AsyncClient, org_id: str) -> None:
    """Mark all context blocks for an org as stale."""
    await (
        client.table("memory_context")
        .update({"is_stale": True})
        .eq("org_id", org_id)
        .execute()
    )


async def search_facts(
    client: AsyncClient,
    org_id: str,
    query: str,
    category: str | None = None,
    limit: int = 20,
) -> list[MemoryFact]:
    """Search facts by keyword (ILIKE) with optional category filter."""
    q = (
        client.table("memory_facts")
        .select("*")
        .eq("org_id", org_id)
        .eq("is_archived", False)
        .ilike("content", f"%{query}%")
    )
    if category:
        q = q.eq("category", category)
    result = await q.order("confidence", desc=True).limit(limit).execute()
    return [MemoryFact.model_validate(row) for row in result.data]


async def archive_fact(client: AsyncClient, fact_id: str) -> None:
    """Archive a fact (soft delete)."""
    await (
        client.table("memory_facts")
        .update({"is_archived": True, "updated_at": datetime.now(UTC).isoformat()})
        .eq("id", fact_id)
        .execute()
    )


async def get_recent_events(
    client: AsyncClient,
    org_id: str,
    limit: int = 20,
) -> list[dict]:
    """Load the most recent memory events for an org."""
    result = (
        await client.table("memory_events")
        .select("*")
        .eq("org_id", org_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data
