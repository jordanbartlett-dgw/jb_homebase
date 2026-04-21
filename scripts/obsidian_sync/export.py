from __future__ import annotations

import hashlib
from pathlib import Path

import structlog
import yaml
from supabase._async.client import AsyncClient

from jordan_claw.db.obsidian import get_pending_exports, mark_note_synced

log = structlog.get_logger()


def _render_note_file(note) -> str:
    """Render a full markdown file from a note (frontmatter + body)."""
    fm = dict(note.frontmatter)
    frontmatter_str = yaml.dump(fm, default_flow_style=False, allow_unicode=True)
    return f"---\n{frontmatter_str}---\n\n{note.content}"


async def export_notes(
    db: AsyncClient,
    org_id: str,
    vault_path: str,
) -> dict:
    """Export Claw-created notes to the vault. Returns stats dict."""
    stats = {"exported": 0}
    vault = Path(vault_path)

    pending = await get_pending_exports(db, org_id)

    for note in pending:
        file_path = vault / note.vault_path
        file_path.parent.mkdir(parents=True, exist_ok=True)

        file_content = _render_note_file(note)
        file_path.write_text(file_content, encoding="utf-8")

        content_hash = hashlib.sha256(file_content.encode()).hexdigest()
        await mark_note_synced(db, note.id, content_hash)

        stats["exported"] += 1
        log.info("note_exported", vault_path=note.vault_path)

    log.info("export_complete", **stats)
    return stats
