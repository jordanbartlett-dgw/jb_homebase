from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts.obsidian_sync.ingest import ingest_vault

VAULT_DIR = "/tmp/test_vault"


@pytest.fixture
def test_vault(tmp_path):
    """Create a minimal test vault structure."""
    notes_dir = tmp_path / "30-Notes"
    notes_dir.mkdir()
    sources_dir = tmp_path / "20-Sources"
    sources_dir.mkdir()
    stories_dir = tmp_path / "15-Stories"
    stories_dir.mkdir()

    (notes_dir / "Test Concept.md").write_text(
        "---\ntype: atomic-note\ntags: [test]\n---\n\nBody of the concept."
    )
    (sources_dir / "Article - Test.md").write_text(
        '---\ntype: source\ntitle: "Test Article"\ntags: [ai]\n---\n\n## Summary\n\nTest.'
    )

    return str(tmp_path)


@pytest.mark.asyncio
@patch("scripts.obsidian_sync.ingest.generate_embeddings")
@patch("scripts.obsidian_sync.ingest.insert_chunks")
@patch("scripts.obsidian_sync.ingest.insert_note")
@patch("scripts.obsidian_sync.ingest.get_notes_by_vault_paths")
async def test_ingest_new_notes(mock_get_existing, mock_insert, mock_chunks, mock_embed, test_vault):
    mock_get_existing.return_value = {}
    mock_insert.return_value = {"id": "new-note-id"}
    mock_embed.return_value = [[0.1] * 512]

    db = AsyncMock()
    stats = await ingest_vault(db, org_id="org-1", vault_path=test_vault, openai_api_key="key")

    assert stats["inserted"] == 2
    assert stats["skipped"] == 0
    assert stats["updated"] == 0
    assert mock_insert.call_count == 2


@pytest.mark.asyncio
@patch("scripts.obsidian_sync.ingest.generate_embeddings")
@patch("scripts.obsidian_sync.ingest.insert_chunks")
@patch("scripts.obsidian_sync.ingest.insert_note")
@patch("scripts.obsidian_sync.ingest.get_notes_by_vault_paths")
async def test_ingest_skips_unchanged(mock_get_existing, mock_insert, mock_chunks, mock_embed, test_vault):
    # Read the file to get its real hash
    import hashlib

    note_path = Path(test_vault) / "30-Notes" / "Test Concept.md"
    content = note_path.read_text()
    real_hash = hashlib.sha256(content.encode()).hexdigest()

    mock_get_existing.return_value = {
        "30-Notes/Test Concept.md": {
            "id": "existing-id",
            "content_hash": real_hash,
            "source_origin": "vault",
        }
    }
    mock_insert.return_value = {"id": "new-id"}
    mock_embed.return_value = [[0.1] * 512]

    db = AsyncMock()
    stats = await ingest_vault(db, org_id="org-1", vault_path=test_vault, openai_api_key="key")

    assert stats["skipped"] == 1
    assert stats["inserted"] == 1  # The source note is new


@pytest.mark.asyncio
@patch("scripts.obsidian_sync.ingest.generate_embeddings")
@patch("scripts.obsidian_sync.ingest.insert_chunks")
@patch("scripts.obsidian_sync.ingest.delete_chunks_for_note")
@patch("scripts.obsidian_sync.ingest.update_note")
@patch("scripts.obsidian_sync.ingest.get_notes_by_vault_paths")
async def test_ingest_updates_changed(mock_get_existing, mock_update, mock_del_chunks, mock_chunks, mock_embed, test_vault):
    mock_get_existing.return_value = {
        "30-Notes/Test Concept.md": {
            "id": "existing-id",
            "content_hash": "old-hash-that-doesnt-match",
            "source_origin": "vault",
        }
    }
    mock_embed.return_value = [[0.1] * 512]

    db = AsyncMock()
    stats = await ingest_vault(db, org_id="org-1", vault_path=test_vault, openai_api_key="key")

    assert stats["updated"] == 1
    mock_update.assert_called_once()
    mock_del_chunks.assert_called_once_with(db, "existing-id")


@pytest.mark.asyncio
@patch("scripts.obsidian_sync.ingest.generate_embeddings")
@patch("scripts.obsidian_sync.ingest.archive_note")
@patch("scripts.obsidian_sync.ingest.insert_note")
@patch("scripts.obsidian_sync.ingest.insert_chunks")
@patch("scripts.obsidian_sync.ingest.get_notes_by_vault_paths")
async def test_ingest_archives_deleted(mock_get_existing, mock_chunks, mock_insert, mock_archive, mock_embed, test_vault):
    mock_get_existing.return_value = {
        "30-Notes/Test Concept.md": {
            "id": "existing-id",
            "content_hash": "whatever",
            "source_origin": "vault",
        },
        "30-Notes/Deleted Note.md": {
            "id": "deleted-id",
            "content_hash": "whatever",
            "source_origin": "vault",
        },
    }
    mock_insert.return_value = {"id": "new-id"}
    mock_embed.return_value = [[0.1] * 512]

    db = AsyncMock()
    stats = await ingest_vault(db, org_id="org-1", vault_path=test_vault, openai_api_key="key")

    assert stats["archived"] == 1
    mock_archive.assert_called_once_with(db, "deleted-id")
