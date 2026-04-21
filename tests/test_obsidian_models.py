from __future__ import annotations

from jordan_claw.obsidian.models import ObsidianNote, ObsidianNoteChunk


def test_obsidian_note_from_db_row():
    row = {
        "id": "abc-123",
        "org_id": "org-1",
        "vault_path": "30-Notes/Test Note.md",
        "title": "Test Note",
        "note_type": "atomic-note",
        "content": "Some content",
        "frontmatter": {"type": "atomic-note", "tags": ["test"]},
        "tags": ["test"],
        "wiki_links": ["Other Note"],
        "source_origin": "vault",
        "sync_status": "synced",
        "content_hash": "abc123hash",
        "is_archived": False,
        "created_at": "2026-04-04T00:00:00+00:00",
        "updated_at": "2026-04-04T00:00:00+00:00",
    }
    note = ObsidianNote.model_validate(row)
    assert note.title == "Test Note"
    assert note.note_type == "atomic-note"
    assert note.tags == ["test"]
    assert note.wiki_links == ["Other Note"]
    assert note.source_origin == "vault"
    assert note.is_archived is False


def test_obsidian_note_defaults():
    note = ObsidianNote(
        id="abc-123",
        org_id="org-1",
        vault_path="20-Sources/Article.md",
        title="Article",
        note_type="source",
        content="Body text",
        frontmatter={"type": "source"},
        content_hash="hash123",
        created_at="2026-04-04T00:00:00+00:00",
        updated_at="2026-04-04T00:00:00+00:00",
    )
    assert note.tags == []
    assert note.wiki_links == []
    assert note.source_origin == "vault"
    assert note.sync_status == "synced"


def test_obsidian_note_chunk_from_db_row():
    row = {
        "id": "chunk-1",
        "note_id": "note-1",
        "chunk_index": 0,
        "content": "Chunk text here",
        "token_count": 42,
        "created_at": "2026-04-04T00:00:00+00:00",
    }
    chunk = ObsidianNoteChunk.model_validate(row)
    assert chunk.note_id == "note-1"
    assert chunk.chunk_index == 0
    assert chunk.token_count == 42
