from __future__ import annotations

from supabase._async.client import AsyncClient

from jordan_claw.db.memory import (
    get_active_facts,
    get_memory_context,
    get_recent_events,
    upsert_memory_context,
)
from jordan_claw.memory.models import MemoryFact

# Category display names, ordered for rendering
CATEGORY_LABELS = {
    "preference": "Preferences",
    "decision": "Decisions",
    "entity": "Entities",
    "workflow": "Workflows",
    "relationship": "Relationships",
}

# Rough estimate: 1 token ≈ 4 chars
CHARS_PER_TOKEN = 4


def render_context_block(
    facts: list[MemoryFact],
    events: list[dict],
    max_tokens: int = 500,
) -> str:
    """Render facts and events into a markdown context block for system prompt injection."""
    if not facts and not events:
        return ""

    max_chars = max_tokens * CHARS_PER_TOKEN

    # Group facts by category, sorted by confidence descending within each group
    grouped: dict[str, list[MemoryFact]] = {}
    for fact in sorted(facts, key=lambda f: f.confidence, reverse=True):
        grouped.setdefault(fact.category, []).append(fact)

    lines = ["## Memory Context", ""]
    char_count = 20  # Header chars

    # Render facts by category
    for category, label in CATEGORY_LABELS.items():
        category_facts = grouped.get(category, [])
        if not category_facts:
            continue

        section_header = f"### {label}"
        char_count += len(section_header) + 1
        if char_count > max_chars:
            break

        lines.append(section_header)
        for fact in category_facts:
            line = f"- {fact.content}"
            char_count += len(line) + 1
            if char_count > max_chars:
                break
            lines.append(line)
        lines.append("")

    # Render recent events
    if events and char_count < max_chars:
        lines.append("### Recent Activity")
        for event in events[:10]:
            created = event.get("created_at", "")[:10]
            date_str = created[5:] if len(created) >= 10 else ""
            line = f"- [{date_str}] {event['summary']}"
            char_count += len(line) + 1
            if char_count > max_chars:
                break
            lines.append(line)
        lines.append("")

    return "\n".join(lines).strip()


async def load_memory_context(
    db: AsyncClient,
    org_id: str,
    scope: str = "global",
) -> str:
    """Load the memory context block, recomputing if stale or missing."""
    cached = await get_memory_context(db, org_id, scope=scope)

    if cached and not cached["is_stale"]:
        return cached["context_block"]

    # Recompute from facts + events
    facts = await get_active_facts(db, org_id)
    events = await get_recent_events(db, org_id, limit=20)
    context_block = render_context_block(facts, events)

    # Cache the result
    await upsert_memory_context(db, org_id, scope=scope, context_block=context_block)

    return context_block
