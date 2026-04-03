from __future__ import annotations

from pydantic_ai import RunContext

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.db.memory import archive_fact, search_facts


async def recall_memory(
    ctx: RunContext[AgentDeps],
    query: str,
    category: str | None = None,
) -> str:
    """Search memory for specific facts. Use when asked 'what do you know about...'
    or when you need deeper context than what's in your memory summary."""
    facts = await search_facts(
        ctx.deps.supabase_client, ctx.deps.org_id, query=query, category=category
    )

    if not facts:
        return "No matching memories found."

    lines = [f"Found {len(facts)} memory fact(s):", ""]
    for fact in facts:
        lines.append(f"- [{fact.category}] {fact.content} (confidence: {fact.confidence})")
    return "\n".join(lines)


async def forget_memory(
    ctx: RunContext[AgentDeps],
    query: str,
) -> str:
    """Forget (archive) a memory fact. Searches by keyword and archives the match.
    If multiple matches, lists them for the user to clarify."""
    facts = await search_facts(ctx.deps.supabase_client, ctx.deps.org_id, query=query)

    if not facts:
        return "No matching memories found to forget."

    if len(facts) == 1:
        await archive_fact(ctx.deps.supabase_client, facts[0].id)
        return f"Forgot: {facts[0].content}"

    lines = [
        f"Found {len(facts)} matching memories. Please be more specific about which to forget:",
        "",
    ]
    for fact in facts:
        lines.append(f"- {fact.content}")
    return "\n".join(lines)
