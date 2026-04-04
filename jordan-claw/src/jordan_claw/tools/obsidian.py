from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import yaml
from pydantic_ai import RunContext

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.db.obsidian import get_note_by_title, insert_chunks, insert_note, search_notes_semantic
from jordan_claw.obsidian.embeddings import chunk_text, generate_embeddings

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


async def read_note(
    ctx: RunContext[AgentDeps],
    title: str,
) -> str:
    """Read the full content of an Obsidian note by title.
    Returns the complete note body, tags, and linked notes."""
    notes = await get_note_by_title(
        ctx.deps.supabase_client, ctx.deps.org_id, title
    )

    if not notes:
        return f"No notes found matching '{title}'."

    if len(notes) == 1:
        note = notes[0]
        tags_str = ", ".join(note.tags) if note.tags else "none"
        links_str = ", ".join(note.wiki_links) if note.wiki_links else "none"
        return (
            f"# {note.title}\n"
            f"**Type:** {note.note_type} | **Tags:** {tags_str}\n"
            f"**Links:** {links_str}\n\n"
            f"{note.content}"
        )

    # Multiple matches: list them for disambiguation
    lines = [f"Multiple notes match '{title}'. Please specify:", ""]
    for note in notes:
        lines.append(f"- **{note.title}** ({note.note_type})")
    return "\n".join(lines)


def _render_source_note_markdown(
    summary: str,
    key_takeaways: list[str],
) -> str:
    """Render the markdown body for a source note (excluding frontmatter)."""
    lines = [
        "## Summary",
        "",
        summary,
        "",
        "## Key Takeaways",
        "",
    ]
    for i, takeaway in enumerate(key_takeaways, 1):
        lines.append(f"{i}. {takeaway}")
    lines.extend([
        "",
        "## Related Topics",
        "",
        "",
        "## Notes",
        "",
    ])
    return "\n".join(lines)


async def create_source_note(
    ctx: RunContext[AgentDeps],
    title: str,
    url: str,
    author: str,
    source_type: str,
    tags: list[str],
    summary: str,
    key_takeaways: list[str],
) -> str:
    """Create a new source note in the Obsidian knowledge base.
    The note will appear in the vault after the next sync."""
    today = datetime.now(UTC).strftime("%Y-%m-%d")

    frontmatter = {
        "type": "source",
        "title": title,
        "url": url,
        "author": author,
        "source-type": source_type,
        "captured": today,
        "tags": tags,
        "status": "processed",
    }

    content = _render_source_note_markdown(summary, key_takeaways)
    vault_path = f"20-Sources/{title}.md"

    # Build the full file content for hashing (frontmatter + body)
    full_file = f"---\n{yaml.dump(frontmatter, default_flow_style=False)}---\n\n{content}"
    content_hash = hashlib.sha256(full_file.encode()).hexdigest()

    note_row = await insert_note(
        ctx.deps.supabase_client,
        org_id=ctx.deps.org_id,
        vault_path=vault_path,
        title=title,
        note_type="source",
        content=content,
        frontmatter=frontmatter,
        tags=tags,
        wiki_links=[],
        content_hash=content_hash,
        source_origin="claw",
        sync_status="pending_export",
    )

    # Generate chunks and embeddings
    chunks = chunk_text(content)
    embeddings = await generate_embeddings(
        [c["content"] for c in chunks],
        api_key=ctx.deps.openai_api_key,
    )

    note_id = note_row.get("id", "")
    chunk_rows = [
        {
            "note_id": note_id,
            "chunk_index": c["chunk_index"],
            "content": c["content"],
            "embedding": embeddings[i],
            "token_count": c["token_count"],
        }
        for i, c in enumerate(chunks)
    ]
    await insert_chunks(ctx.deps.supabase_client, chunk_rows)

    return f"Source note '{title}' created. It will appear in your vault after the next sync."
