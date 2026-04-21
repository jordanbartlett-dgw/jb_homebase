from __future__ import annotations

from datetime import UTC, datetime

import structlog
from supabase._async.client import AsyncClient

from jordan_claw.obsidian.models import ObsidianNote

log = structlog.get_logger()


async def insert_note(
    client: AsyncClient,
    *,
    org_id: str,
    vault_path: str,
    title: str,
    note_type: str,
    content: str,
    frontmatter: dict,
    tags: list[str],
    wiki_links: list[str],
    content_hash: str,
    source_origin: str = "vault",
    sync_status: str = "synced",
) -> dict:
    """Insert a new obsidian note."""
    result = await (
        client.table("obsidian_notes")
        .insert({
            "org_id": org_id,
            "vault_path": vault_path,
            "title": title,
            "note_type": note_type,
            "content": content,
            "frontmatter": frontmatter,
            "tags": tags,
            "wiki_links": wiki_links,
            "content_hash": content_hash,
            "source_origin": source_origin,
            "sync_status": sync_status,
        })
        .execute()
    )
    return result.data[0] if result.data else {}


async def update_note(
    client: AsyncClient,
    note_id: str,
    *,
    content: str,
    frontmatter: dict,
    tags: list[str],
    wiki_links: list[str],
    content_hash: str,
) -> None:
    """Update an existing obsidian note."""
    await (
        client.table("obsidian_notes")
        .update({
            "content": content,
            "frontmatter": frontmatter,
            "tags": tags,
            "wiki_links": wiki_links,
            "content_hash": content_hash,
            "updated_at": datetime.now(UTC).isoformat(),
        })
        .eq("id", note_id)
        .execute()
    )


async def get_note_by_title(
    client: AsyncClient,
    org_id: str,
    title: str,
) -> list[ObsidianNote]:
    """Find notes by title (case-insensitive)."""
    result = await (
        client.table("obsidian_notes")
        .select("*")
        .eq("org_id", org_id)
        .eq("is_archived", False)
        .ilike("title", f"%{title}%")
        .limit(10)
        .execute()
    )
    return [ObsidianNote.model_validate(row) for row in result.data]


async def get_notes_by_vault_paths(
    client: AsyncClient,
    org_id: str,
) -> dict[str, dict]:
    """Load all non-archived notes for an org, keyed by vault_path.

    Returns dict mapping vault_path to {id, content_hash} for sync diffing.
    """
    result = await (
        client.table("obsidian_notes")
        .select("id, vault_path, content_hash, source_origin")
        .eq("org_id", org_id)
        .eq("is_archived", False)
        .execute()
    )
    return {
        row["vault_path"]: {
            "id": row["id"],
            "content_hash": row["content_hash"],
            "source_origin": row["source_origin"],
        }
        for row in result.data
    }


async def archive_note(client: AsyncClient, note_id: str) -> None:
    """Soft-delete a note by marking it archived."""
    await (
        client.table("obsidian_notes")
        .update({
            "is_archived": True,
            "updated_at": datetime.now(UTC).isoformat(),
        })
        .eq("id", note_id)
        .execute()
    )


async def insert_chunks(client: AsyncClient, chunks: list[dict]) -> None:
    """Insert embedding chunks for a note."""
    await client.table("obsidian_note_chunks").insert(chunks).execute()


async def delete_chunks_for_note(client: AsyncClient, note_id: str) -> None:
    """Delete all chunks for a note (before re-embedding)."""
    await (
        client.table("obsidian_note_chunks")
        .delete()
        .eq("note_id", note_id)
        .execute()
    )


async def get_pending_exports(
    client: AsyncClient,
    org_id: str,
) -> list[ObsidianNote]:
    """Get notes created by Claw that haven't been exported to vault."""
    result = await (
        client.table("obsidian_notes")
        .select("*")
        .eq("org_id", org_id)
        .eq("sync_status", "pending_export")
        .execute()
    )
    return [ObsidianNote.model_validate(row) for row in result.data]


async def mark_note_synced(
    client: AsyncClient,
    note_id: str,
    content_hash: str,
) -> None:
    """Mark a note as synced after export to vault."""
    await (
        client.table("obsidian_notes")
        .update({
            "sync_status": "synced",
            "content_hash": content_hash,
            "updated_at": datetime.now(UTC).isoformat(),
        })
        .eq("id", note_id)
        .execute()
    )


async def search_notes_semantic(
    client: AsyncClient,
    org_id: str,
    embedding: list[float],
    note_type: str | None = None,
    tags: list[str] | None = None,
    limit: int = 10,
) -> list[dict]:
    """Semantic search over note chunks using cosine similarity.

    Calls a Supabase RPC function that handles the vector search + join.
    """
    params: dict = {
        "p_org_id": org_id,
        "p_embedding": embedding,
        "p_limit": limit,
    }
    if note_type:
        params["p_note_type"] = note_type
    if tags:
        params["p_tags"] = tags

    result = await client.rpc("search_obsidian_notes", params).execute()
    return result.data
