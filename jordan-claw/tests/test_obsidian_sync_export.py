from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from jordan_claw.obsidian.models import ObsidianNote
from scripts.obsidian_sync.export import export_notes


@pytest.fixture
def test_vault(tmp_path):
    """Create a minimal vault directory for export."""
    sources_dir = tmp_path / "20-Sources"
    sources_dir.mkdir()
    return str(tmp_path)


def _make_claw_note() -> ObsidianNote:
    return ObsidianNote(
        id="note-1",
        org_id="org-1",
        vault_path="20-Sources/New Article.md",
        title="New Article",
        note_type="source",
        content="## Summary\n\nA summary.\n\n## Key Takeaways\n\n1. Point one\n\n## Related Topics\n\n\n## Notes\n",
        frontmatter={
            "type": "source",
            "title": "New Article",
            "url": "https://example.com",
            "author": "Author",
            "source-type": "article",
            "captured": "2026-04-04",
            "tags": ["ai"],
            "status": "processed",
        },
        tags=["ai"],
        wiki_links=[],
        source_origin="claw",
        sync_status="pending_export",
        content_hash="placeholder",
        created_at="2026-04-04T00:00:00+00:00",
        updated_at="2026-04-04T00:00:00+00:00",
    )


@pytest.mark.asyncio
@patch("scripts.obsidian_sync.export.mark_note_synced")
@patch("scripts.obsidian_sync.export.get_pending_exports")
async def test_export_writes_file(mock_get_pending, mock_mark_synced, test_vault):
    mock_get_pending.return_value = [_make_claw_note()]

    db = AsyncMock()
    stats = await export_notes(db, org_id="org-1", vault_path=test_vault)

    assert stats["exported"] == 1

    written_file = Path(test_vault) / "20-Sources" / "New Article.md"
    assert written_file.exists()

    content = written_file.read_text()
    assert "type: source" in content
    assert "## Summary" in content
    assert "A summary." in content

    mock_mark_synced.assert_called_once()


@pytest.mark.asyncio
@patch("scripts.obsidian_sync.export.mark_note_synced")
@patch("scripts.obsidian_sync.export.get_pending_exports")
async def test_export_no_pending(mock_get_pending, mock_mark_synced, test_vault):
    mock_get_pending.return_value = []

    db = AsyncMock()
    stats = await export_notes(db, org_id="org-1", vault_path=test_vault)

    assert stats["exported"] == 0
    mock_mark_synced.assert_not_called()


@pytest.mark.asyncio
@patch("scripts.obsidian_sync.export.mark_note_synced")
@patch("scripts.obsidian_sync.export.get_pending_exports")
async def test_export_creates_parent_dirs(mock_get_pending, mock_mark_synced, test_vault):
    """Export should create parent directories if they don't exist."""
    note = _make_claw_note()
    note.vault_path = "20-Sources/Subfolder/Deep Article.md"
    mock_get_pending.return_value = [note]

    db = AsyncMock()
    await export_notes(db, org_id="org-1", vault_path=test_vault)

    written_file = Path(test_vault) / "20-Sources" / "Subfolder" / "Deep Article.md"
    assert written_file.exists()
