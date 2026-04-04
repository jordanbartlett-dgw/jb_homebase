from __future__ import annotations

from pydantic import BaseModel, Field


class ObsidianNote(BaseModel):
    """A note row from the obsidian_notes table."""

    id: str
    org_id: str
    vault_path: str
    title: str
    note_type: str
    content: str
    frontmatter: dict = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    wiki_links: list[str] = Field(default_factory=list)
    source_origin: str = "vault"
    sync_status: str = "synced"
    content_hash: str
    is_archived: bool = False
    created_at: str
    updated_at: str


class ObsidianNoteChunk(BaseModel):
    """A chunk row from the obsidian_note_chunks table."""

    id: str
    note_id: str
    chunk_index: int = 0
    content: str
    token_count: int = 0
    created_at: str
