"""Seed the eval-only Obsidian corpus into Supabase.

Reads `evals/fixtures/corpus.yaml`, ensures the eva organization row exists,
then idempotently rewrites every eva note keyed on (org_id, vault_path).

Usage:
    uv run python -m evals.seed_corpus
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import structlog
import yaml

from jordan_claw.config import get_settings
from jordan_claw.db.obsidian import (
    delete_chunks_for_note,
    get_notes_by_vault_paths,
    insert_chunks,
    insert_note,
    update_note,
)
from jordan_claw.obsidian.embeddings import chunk_text, generate_embeddings
from supabase import create_async_client

log = structlog.get_logger()

CORPUS_PATH = Path(__file__).parent / "fixtures" / "corpus.yaml"
EVA_ORG_NAME = "Eval Test Org"
EVA_ORG_SLUG = "eval-test-org"


def _vault_path(slug: str) -> str:
    return f"evals/{slug}.md"


def _content_hash(body: str, frontmatter: dict) -> str:
    # frontmatter dict is small + deterministic enough; sort keys for stability
    fm_str = yaml.dump(frontmatter, default_flow_style=False, sort_keys=True)
    return hashlib.sha256(f"{fm_str}\n{body}".encode()).hexdigest()


async def _ensure_eva_org(client) -> None:
    settings = get_settings()
    existing = (
        await client.table("organizations")
        .select("id")
        .eq("id", settings.eval_test_org_id)
        .limit(1)
        .execute()
    )
    if existing.data:
        return
    await client.table("organizations").insert(
        {
            "id": settings.eval_test_org_id,
            "name": EVA_ORG_NAME,
            "slug": EVA_ORG_SLUG,
        }
    ).execute()
    log.info("eva_org_created", org_id=settings.eval_test_org_id)


async def seed() -> int:
    settings = get_settings()
    corpus = yaml.safe_load(CORPUS_PATH.read_text())
    notes = corpus["notes"]

    client = await create_async_client(settings.supabase_url, settings.supabase_service_key)

    await _ensure_eva_org(client)

    # Generate embeddings up-front in a single batch.
    # Each note body is short; one chunk per note in practice.
    bodies = [n["body"] for n in notes]
    log.info("embedding_corpus", count=len(bodies))
    embeddings = await generate_embeddings(bodies, api_key=settings.openai_api_key)

    existing_by_path = await get_notes_by_vault_paths(client, settings.eval_test_org_id)

    for note, embedding in zip(notes, embeddings, strict=True):
        slug = note["slug"]
        vault_path = _vault_path(slug)
        body = note["body"]
        frontmatter = {
            "type": note["note_type"],
            "title": note["title"],
            "tags": note["tags"],
            "slug": slug,
        }
        chash = _content_hash(body, frontmatter)
        chunks = chunk_text(body)

        if vault_path in existing_by_path:
            existing = existing_by_path[vault_path]
            if existing["content_hash"] == chash:
                log.info("note_unchanged", slug=slug)
                continue
            note_id = existing["id"]
            await update_note(
                client,
                note_id,
                content=body,
                frontmatter=frontmatter,
                tags=note["tags"],
                wiki_links=[],
                content_hash=chash,
            )
            await delete_chunks_for_note(client, note_id)
            log.info("note_updated", slug=slug)
        else:
            row = await insert_note(
                client,
                org_id=settings.eval_test_org_id,
                vault_path=vault_path,
                title=note["title"],
                note_type=note["note_type"],
                content=body,
                frontmatter=frontmatter,
                tags=note["tags"],
                wiki_links=[],
                content_hash=chash,
                source_origin="vault",
                sync_status="synced",
            )
            note_id = row["id"]
            log.info("note_inserted", slug=slug)

        # Each fixture is short enough to chunk into a single chunk in practice.
        # If a future fixture ever produces multiple chunks, re-embed per chunk
        # so we never store an embedding that doesn't match the chunk content.
        if len(chunks) == 1:
            chunk_embeddings = [embedding]
        else:
            chunk_embeddings = await generate_embeddings(
                [c["content"] for c in chunks],
                api_key=settings.openai_api_key,
            )

        chunk_rows = [
            {
                "note_id": note_id,
                "chunk_index": chunks[i]["chunk_index"],
                "content": chunks[i]["content"],
                "embedding": chunk_embeddings[i],
                "token_count": chunks[i]["token_count"],
            }
            for i in range(len(chunks))
        ]

        await insert_chunks(client, chunk_rows)

    return len(notes)


def main() -> None:
    count = asyncio.run(seed())
    print(f"Seeded {count} eval-corpus notes.")


if __name__ == "__main__":
    main()
