from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from jordan_claw.db.obsidian import (
    delete_chunks_for_note,
    get_note_by_title,
    get_pending_exports,
    insert_chunks,
    insert_note,
    search_notes_semantic,
    update_note,
)
from jordan_claw.obsidian.models import ObsidianNote


def _mock_db(data: list | None = None) -> MagicMock:
    """Build a mock Supabase client with chainable query builder."""
    if data is None:
        data = []

    mock_execute = AsyncMock(return_value=MagicMock(data=data))

    builder = MagicMock()
    builder.select.return_value = builder
    builder.insert.return_value = builder
    builder.update.return_value = builder
    builder.delete.return_value = builder
    builder.upsert.return_value = builder
    builder.eq.return_value = builder
    builder.neq.return_value = builder
    builder.ilike.return_value = builder
    builder.contains.return_value = builder
    builder.overlap.return_value = builder
    builder.order.return_value = builder
    builder.limit.return_value = builder
    builder.execute = mock_execute

    db = MagicMock()
    db.table.return_value = builder
    return db


@pytest.mark.asyncio
async def test_insert_note():
    db = _mock_db()
    await insert_note(
        db,
        org_id="org-1",
        vault_path="30-Notes/Test.md",
        title="Test",
        note_type="atomic-note",
        content="Body",
        frontmatter={"type": "atomic-note"},
        tags=["test"],
        wiki_links=["Other"],
        content_hash="abc123",
        source_origin="vault",
        sync_status="synced",
    )
    db.table.assert_called_with("obsidian_notes")
    call_args = db.table.return_value.insert.call_args[0][0]
    assert call_args["title"] == "Test"
    assert call_args["org_id"] == "org-1"


@pytest.mark.asyncio
async def test_update_note():
    db = _mock_db()
    await update_note(
        db,
        note_id="note-1",
        content="Updated body",
        frontmatter={"type": "source"},
        tags=["updated"],
        wiki_links=["New Link"],
        content_hash="newhash",
    )
    db.table.assert_called_with("obsidian_notes")
    db.table.return_value.update.assert_called_once()
    db.table.return_value.eq.assert_called_with("id", "note-1")


@pytest.mark.asyncio
async def test_get_note_by_title_found():
    row = {
        "id": "note-1",
        "org_id": "org-1",
        "vault_path": "30-Notes/Test.md",
        "title": "Test Note",
        "note_type": "atomic-note",
        "content": "Body",
        "frontmatter": {},
        "tags": [],
        "wiki_links": [],
        "source_origin": "vault",
        "sync_status": "synced",
        "content_hash": "hash",
        "is_archived": False,
        "created_at": "2026-04-04T00:00:00+00:00",
        "updated_at": "2026-04-04T00:00:00+00:00",
    }
    db = _mock_db(data=[row])
    notes = await get_note_by_title(db, "org-1", "Test Note")
    assert len(notes) == 1
    assert notes[0].title == "Test Note"


@pytest.mark.asyncio
async def test_get_note_by_title_not_found():
    db = _mock_db(data=[])
    notes = await get_note_by_title(db, "org-1", "Missing")
    assert notes == []


@pytest.mark.asyncio
async def test_insert_chunks():
    db = _mock_db()
    chunks = [
        {"note_id": "note-1", "chunk_index": 0, "content": "text", "embedding": [0.1] * 512, "token_count": 10},
    ]
    await insert_chunks(db, chunks)
    db.table.assert_called_with("obsidian_note_chunks")
    db.table.return_value.insert.assert_called_once()


@pytest.mark.asyncio
async def test_delete_chunks_for_note():
    db = _mock_db()
    await delete_chunks_for_note(db, "note-1")
    db.table.assert_called_with("obsidian_note_chunks")
    db.table.return_value.delete.assert_called_once()
    db.table.return_value.eq.assert_called_with("note_id", "note-1")


@pytest.mark.asyncio
async def test_get_pending_exports():
    row = {
        "id": "note-1",
        "org_id": "org-1",
        "vault_path": "20-Sources/Article.md",
        "title": "Article",
        "note_type": "source",
        "content": "Body",
        "frontmatter": {},
        "tags": [],
        "wiki_links": [],
        "source_origin": "claw",
        "sync_status": "pending_export",
        "content_hash": "hash",
        "is_archived": False,
        "created_at": "2026-04-04T00:00:00+00:00",
        "updated_at": "2026-04-04T00:00:00+00:00",
    }
    db = _mock_db(data=[row])
    notes = await get_pending_exports(db, "org-1")
    assert len(notes) == 1
    assert notes[0].sync_status == "pending_export"


@pytest.mark.asyncio
async def test_search_notes_semantic():
    # search_notes_semantic uses RPC, so mock differently
    db = MagicMock()
    rpc_builder = MagicMock()
    rpc_builder.execute = AsyncMock(
        return_value=MagicMock(data=[
            {
                "note_id": "note-1",
                "title": "Test",
                "note_type": "atomic-note",
                "tags": ["test"],
                "chunk_content": "matching text",
                "similarity": 0.85,
            }
        ])
    )
    db.rpc.return_value = rpc_builder
    results = await search_notes_semantic(
        db, org_id="org-1", embedding=[0.1] * 512
    )
    assert len(results) == 1
    assert results[0]["similarity"] == 0.85
