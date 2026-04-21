from __future__ import annotations

from pathlib import Path

import structlog
from supabase._async.client import AsyncClient

from jordan_claw.db.obsidian import (
    archive_note,
    delete_chunks_for_note,
    get_notes_by_vault_paths,
    insert_chunks,
    insert_note,
    update_note,
)
from openai import AsyncOpenAI

from jordan_claw.obsidian.embeddings import chunk_text, generate_embeddings
from jordan_claw.obsidian.parser import parse_note_file

log = structlog.get_logger()

TARGET_FOLDERS = ["30-Notes", "20-Sources", "15-Stories"]


async def ingest_vault(
    db: AsyncClient,
    org_id: str,
    vault_path: str,
    openai_api_key: str,
) -> dict:
    """Ingest vault notes into Supabase. Returns stats dict."""
    stats = {"inserted": 0, "updated": 0, "skipped": 0, "archived": 0}
    vault = Path(vault_path)
    openai_client = AsyncOpenAI(api_key=openai_api_key)

    # Load existing notes for diff
    existing = await get_notes_by_vault_paths(db, org_id)

    # Track which vault_paths we see on disk
    seen_paths: set[str] = set()

    for folder in TARGET_FOLDERS:
        folder_path = vault / folder
        if not folder_path.exists():
            continue

        for md_file in sorted(folder_path.rglob("*.md")):
            relative = str(md_file.relative_to(vault))
            seen_paths.add(relative)

            raw_content = md_file.read_text(encoding="utf-8")
            parsed = parse_note_file(raw_content, relative)

            if relative in existing:
                ex = existing[relative]
                if ex["content_hash"] == parsed["content_hash"]:
                    stats["skipped"] += 1
                    continue

                # Content changed: update note, re-embed
                await update_note(
                    db,
                    ex["id"],
                    content=parsed["content"],
                    frontmatter=parsed["frontmatter"],
                    tags=parsed["tags"],
                    wiki_links=parsed["wiki_links"],
                    content_hash=parsed["content_hash"],
                )
                await delete_chunks_for_note(db, ex["id"])
                await _embed_and_insert_chunks(
                    db, ex["id"], parsed["content"], openai_api_key, openai_client
                )
                stats["updated"] += 1
                log.info("note_updated", vault_path=relative)
            else:
                # New note: insert + embed
                note_row = await insert_note(
                    db,
                    org_id=org_id,
                    vault_path=parsed["vault_path"],
                    title=parsed["title"],
                    note_type=parsed["note_type"],
                    content=parsed["content"],
                    frontmatter=parsed["frontmatter"],
                    tags=parsed["tags"],
                    wiki_links=parsed["wiki_links"],
                    content_hash=parsed["content_hash"],
                    source_origin="vault",
                    sync_status="synced",
                )
                note_id = note_row.get("id", "")
                await _embed_and_insert_chunks(
                    db, note_id, parsed["content"], openai_api_key, openai_client
                )
                stats["inserted"] += 1
                log.info("note_inserted", vault_path=relative)

    # Archive notes deleted from vault (only vault-origin notes)
    for path, ex in existing.items():
        if path not in seen_paths and ex["source_origin"] == "vault":
            await archive_note(db, ex["id"])
            stats["archived"] += 1
            log.info("note_archived", vault_path=path)

    log.info("ingest_complete", **stats)
    return stats


async def _embed_and_insert_chunks(
    db: AsyncClient,
    note_id: str,
    content: str,
    openai_api_key: str,
    openai_client: AsyncOpenAI | None = None,
) -> None:
    """Chunk content, generate embeddings, and insert into DB."""
    chunks = chunk_text(content)
    if not chunks or (len(chunks) == 1 and not chunks[0]["content"]):
        return

    texts = [c["content"] for c in chunks if c["content"]]
    if not texts:
        return

    embeddings = await generate_embeddings(texts, api_key=openai_api_key, client=openai_client)

    chunk_rows = [
        {
            "note_id": note_id,
            "chunk_index": c["chunk_index"],
            "content": c["content"],
            "embedding": embeddings[i],
            "token_count": c["token_count"],
        }
        for i, c in enumerate(chunks)
        if c["content"]
    ]
    await insert_chunks(db, chunk_rows)
