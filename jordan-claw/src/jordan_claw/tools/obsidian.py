from __future__ import annotations

from pydantic_ai import RunContext

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.db.obsidian import search_notes_semantic
from jordan_claw.obsidian.embeddings import generate_embeddings

SNIPPET_MAX_CHARS = 800  # ~200 tokens


async def search_notes(
    ctx: RunContext[AgentDeps],
    query: str,
    note_type: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Search Jordan's Obsidian knowledge base by concept or keyword.
    Returns titles, types, tags, and snippets of matching notes.
    Use read_note to get the full content of a specific result."""
    embeddings = await generate_embeddings([query], api_key=ctx.deps.openai_api_key)
    embedding = embeddings[0]

    results = await search_notes_semantic(
        ctx.deps.supabase_client,
        org_id=ctx.deps.org_id,
        embedding=embedding,
        note_type=note_type,
        tags=tags,
    )

    if not results:
        return "No matching notes found."

    lines = [f"Found {len(results)} matching note(s):", ""]
    for r in results:
        snippet = r["chunk_content"][:SNIPPET_MAX_CHARS]
        if len(r["chunk_content"]) > SNIPPET_MAX_CHARS:
            snippet += "..."
        tags_str = ", ".join(r.get("tags") or [])
        lines.append(f"**{r['title']}** ({r['note_type']})")
        lines.append(f"  Tags: {tags_str}")
        lines.append(f"  Similarity: {r['similarity']:.2f}")
        lines.append(f"  Snippet: {snippet}")
        lines.append("")

    return "\n".join(lines)
