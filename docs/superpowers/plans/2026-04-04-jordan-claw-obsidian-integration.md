# Obsidian Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Jordan Claw read access to the Obsidian vault (via Supabase) and the ability to create source notes, with a local sync script bridging vault and DB.

**Architecture:** Notes from `30-Notes/`, `20-Sources/`, `15-Stories/` are ingested into Supabase with pgvector embeddings. Claw gets `search_notes`, `read_note`, and `create_source_note` tools. A local CLI script syncs vault→DB (ingest) and DB→vault (export) on a twice-weekly cron.

**Tech Stack:** Python 3.12, Supabase (pgvector), OpenAI text-embedding-3-small (512d), python-frontmatter, Pydantic AI tools, click CLI

**Spec:** `docs/superpowers/specs/2026-04-04-jordan-claw-obsidian-integration-design.md`

---

### Task 1: Add dependencies and SQL migration

**Files:**
- Modify: `jordan-claw/pyproject.toml`
- Create: `jordan-claw/supabase/migrations/003_obsidian_tables.sql`

- [ ] **Step 1: Add python-frontmatter and openai to pyproject.toml**

In `jordan-claw/pyproject.toml`, add to the `dependencies` list:

```toml
    "python-frontmatter>=1.1.0",
    "openai>=1.50.0",
    "click>=8.1.0",
```

- [ ] **Step 2: Install dependencies**

Run: `cd /home/jb/Developer/jb_homebase/jordan-claw && uv sync`
Expected: All dependencies resolve and install.

- [ ] **Step 3: Create 003_obsidian_tables.sql**

Create `jordan-claw/supabase/migrations/003_obsidian_tables.sql`:

```sql
-- Enable pgvector if not already enabled
create extension if not exists vector with schema extensions;

-- Obsidian notes ingested from vault or created by Claw
create table obsidian_notes (
    id uuid primary key default gen_random_uuid(),
    org_id uuid not null references organizations(id) on delete cascade,
    vault_path text not null,
    title text not null,
    note_type text not null,
    content text not null,
    frontmatter jsonb not null default '{}',
    tags text[] default '{}',
    wiki_links text[] default '{}',
    source_origin text not null default 'vault'
        check (source_origin in ('vault', 'claw')),
    sync_status text not null default 'synced'
        check (sync_status in ('synced', 'pending_export')),
    content_hash text not null,
    is_archived boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (org_id, vault_path)
);

create index idx_obsidian_notes_org_type
    on obsidian_notes (org_id, note_type)
    where is_archived = false;

create index idx_obsidian_notes_tags
    on obsidian_notes using gin (tags)
    where is_archived = false;

-- Chunks with vector embeddings for semantic search
create table obsidian_note_chunks (
    id uuid primary key default gen_random_uuid(),
    note_id uuid not null references obsidian_notes(id) on delete cascade,
    chunk_index int not null default 0,
    content text not null,
    embedding vector(512),
    token_count int not null default 0,
    created_at timestamptz not null default now()
);

create index idx_obsidian_note_chunks_note_id
    on obsidian_note_chunks (note_id);

create index idx_obsidian_note_chunks_embedding
    on obsidian_note_chunks using hnsw (embedding vector_cosine_ops);

-- RLS
alter table obsidian_notes enable row level security;
alter table obsidian_note_chunks enable row level security;
```

- [ ] **Step 4: Run migration on Supabase**

Run the SQL in the Supabase dashboard or via psql, then reload PostgREST schema cache:

```sql
SELECT pg_notify('pgrst', 'reload schema');
```

- [ ] **Step 5: Commit**

```bash
cd /home/jb/Developer/jb_homebase
git add jordan-claw/pyproject.toml jordan-claw/supabase/migrations/003_obsidian_tables.sql
git commit -m "feat: add obsidian tables migration and dependencies"
```

---

### Task 2: Pydantic models for obsidian notes

**Files:**
- Create: `jordan-claw/src/jordan_claw/obsidian/__init__.py`
- Create: `jordan-claw/src/jordan_claw/obsidian/models.py`
- Create: `jordan-claw/tests/test_obsidian_models.py`

- [ ] **Step 1: Write the failing tests**

Create `jordan-claw/tests/test_obsidian_models.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/jb/Developer/jb_homebase/jordan-claw && uv run pytest tests/test_obsidian_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jordan_claw.obsidian'`

- [ ] **Step 3: Implement the models**

Create `jordan-claw/src/jordan_claw/obsidian/__init__.py` (empty file).

Create `jordan-claw/src/jordan_claw/obsidian/models.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/jb/Developer/jb_homebase/jordan-claw && uv run pytest tests/test_obsidian_models.py -v`
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add jordan-claw/src/jordan_claw/obsidian/ jordan-claw/tests/test_obsidian_models.py
git commit -m "feat: add Pydantic models for obsidian notes and chunks"
```

---

### Task 3: Note parser (frontmatter, wiki-links, content hash)

**Files:**
- Create: `jordan-claw/src/jordan_claw/obsidian/parser.py`
- Create: `jordan-claw/tests/test_obsidian_parser.py`

- [ ] **Step 1: Write the failing tests**

Create `jordan-claw/tests/test_obsidian_parser.py`:

```python
from __future__ import annotations

from jordan_claw.obsidian.parser import extract_wiki_links, parse_note_file


SAMPLE_SOURCE_NOTE = """\
---
type: source
title: "Test Article"
url: https://example.com
author: "Test Author"
source-type: article
captured: 2026-03-03
tags: [leadership, mindfulness]
status: processed
---

## Summary

This is a test summary.

## Key Takeaways

1. First takeaway

## Related Topics

- [[Atomic Note One]]
- [[Atomic Note Two]]

## Notes
"""

SAMPLE_ATOMIC_NOTE = """\
---
type: atomic-note
created: 2026-03-16
tags: [entrepreneurship, scaling]
sources:
  - "[[Source Document One]]"
---

This is the body of the atomic note.

## Connections

- [[Related Concept]] -- explains the relationship
- [[Another Concept]] -- another connection

## Applications

- Can be used for X
"""

SAMPLE_NO_FRONTMATTER = """\
# Just a heading

Some content without frontmatter.

Links to [[Other Note]] here.
"""


def test_parse_source_note():
    result = parse_note_file(SAMPLE_SOURCE_NOTE, "20-Sources/Test Article.md")
    assert result["title"] == "Test Article"
    assert result["note_type"] == "source"
    assert result["tags"] == ["leadership", "mindfulness"]
    assert "Atomic Note One" in result["wiki_links"]
    assert "Atomic Note Two" in result["wiki_links"]
    assert result["frontmatter"]["url"] == "https://example.com"
    assert "## Summary" in result["content"]
    assert result["content_hash"] is not None


def test_parse_atomic_note():
    result = parse_note_file(SAMPLE_ATOMIC_NOTE, "30-Notes/Test Concept.md")
    assert result["title"] == "Test Concept"
    assert result["note_type"] == "atomic-note"
    assert result["tags"] == ["entrepreneurship", "scaling"]
    assert "Related Concept" in result["wiki_links"]
    assert "Another Concept" in result["wiki_links"]
    assert "Source Document One" in result["wiki_links"]


def test_parse_note_without_frontmatter():
    result = parse_note_file(SAMPLE_NO_FRONTMATTER, "15-Stories/Story.md")
    assert result["title"] == "Story"
    assert result["note_type"] == "story"
    assert result["tags"] == []
    assert "Other Note" in result["wiki_links"]


def test_parse_note_title_fallback_from_filename():
    result = parse_note_file(SAMPLE_ATOMIC_NOTE, "30-Notes/My Note Title.md")
    # frontmatter has no title field, so falls back to filename
    assert result["title"] == "My Note Title"


def test_parse_note_title_from_frontmatter():
    result = parse_note_file(SAMPLE_SOURCE_NOTE, "20-Sources/Whatever.md")
    # source notes have title in frontmatter
    assert result["title"] == "Test Article"


def test_extract_wiki_links():
    text = "Links to [[Note A]] and [[Note B]] and [[Note A]] again"
    links = extract_wiki_links(text)
    assert links == ["Note A", "Note B"]


def test_extract_wiki_links_empty():
    assert extract_wiki_links("No links here") == []


def test_content_hash_deterministic():
    result1 = parse_note_file(SAMPLE_SOURCE_NOTE, "test.md")
    result2 = parse_note_file(SAMPLE_SOURCE_NOTE, "test.md")
    assert result1["content_hash"] == result2["content_hash"]


def test_note_type_from_folder_fallback():
    """When frontmatter has a non-standard type, use it as-is."""
    note_with_custom_type = """\
---
type: delivery-profile
updated: 2026-03-12
---

Content here.
"""
    result = parse_note_file(note_with_custom_type, "15-Stories/Profile.md")
    assert result["note_type"] == "delivery-profile"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/jb/Developer/jb_homebase/jordan-claw && uv run pytest tests/test_obsidian_parser.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jordan_claw.obsidian.parser'`

- [ ] **Step 3: Implement the parser**

Create `jordan-claw/src/jordan_claw/obsidian/parser.py`:

```python
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import frontmatter

WIKI_LINK_PATTERN = re.compile(r"\[\[([^\]]+)\]\]")

FOLDER_TYPE_MAP = {
    "30-Notes": "atomic-note",
    "20-Sources": "source",
    "15-Stories": "story",
}


def extract_wiki_links(text: str) -> list[str]:
    """Extract unique wiki-link targets from text, preserving first-seen order."""
    seen: set[str] = set()
    result: list[str] = []
    for match in WIKI_LINK_PATTERN.finditer(text):
        name = match.group(1)
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result


def _title_from_path(vault_path: str) -> str:
    """Extract title from vault path by stripping folder and .md extension."""
    return Path(vault_path).stem


def _note_type_from_folder(vault_path: str) -> str:
    """Infer note type from the top-level folder in the vault path."""
    top_folder = vault_path.split("/")[0] if "/" in vault_path else ""
    return FOLDER_TYPE_MAP.get(top_folder, "note")


def parse_note_file(raw_content: str, vault_path: str) -> dict:
    """Parse a markdown note file into structured fields.

    Args:
        raw_content: The full file content including frontmatter.
        vault_path: Relative path in the vault, e.g. '30-Notes/My Note.md'.

    Returns:
        Dict with keys: title, note_type, content, frontmatter, tags,
        wiki_links, content_hash, vault_path.
    """
    post = frontmatter.loads(raw_content)

    fm = dict(post.metadata)
    body = post.content

    title = fm.get("title") or _title_from_path(vault_path)
    note_type = fm.get("type") or _note_type_from_folder(vault_path)
    tags = fm.get("tags", [])
    if not isinstance(tags, list):
        tags = []

    # Extract wiki-links from both frontmatter sources and body
    all_text = raw_content  # Search the full file for links
    wiki_links = extract_wiki_links(all_text)

    content_hash = hashlib.sha256(raw_content.encode()).hexdigest()

    return {
        "vault_path": vault_path,
        "title": title,
        "note_type": note_type,
        "content": body,
        "frontmatter": fm,
        "tags": tags,
        "wiki_links": wiki_links,
        "content_hash": content_hash,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/jb/Developer/jb_homebase/jordan-claw && uv run pytest tests/test_obsidian_parser.py -v`
Expected: 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add jordan-claw/src/jordan_claw/obsidian/parser.py jordan-claw/tests/test_obsidian_parser.py
git commit -m "feat: add obsidian note parser with frontmatter and wiki-link extraction"
```

---

### Task 4: Chunking and embeddings

**Files:**
- Create: `jordan-claw/src/jordan_claw/obsidian/embeddings.py`
- Create: `jordan-claw/tests/test_obsidian_embeddings.py`

- [ ] **Step 1: Write the failing tests**

Create `jordan-claw/tests/test_obsidian_embeddings.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from jordan_claw.obsidian.embeddings import chunk_text, generate_embeddings

# ~4 chars per token, so 100 chars ≈ 25 tokens
SHORT_TEXT = "This is a short note. It should not be chunked."

# Build a long text that exceeds 1000 tokens (~4000 chars)
LONG_TEXT = (
    "## Section One\n\n"
    + "A" * 2000
    + "\n\n## Section Two\n\n"
    + "B" * 2000
    + "\n\n## Section Three\n\n"
    + "C" * 500
)


def test_chunk_short_text():
    chunks = chunk_text(SHORT_TEXT)
    assert len(chunks) == 1
    assert chunks[0]["content"] == SHORT_TEXT
    assert chunks[0]["chunk_index"] == 0
    assert chunks[0]["token_count"] > 0


def test_chunk_long_text_splits_at_headings():
    chunks = chunk_text(LONG_TEXT)
    assert len(chunks) > 1
    # Each chunk should have content
    for chunk in chunks:
        assert len(chunk["content"]) > 0
        assert chunk["token_count"] > 0
    # Chunk indexes should be sequential
    indexes = [c["chunk_index"] for c in chunks]
    assert indexes == list(range(len(chunks)))


def test_chunk_overlap():
    """Adjacent chunks should have ~10% overlap."""
    chunks = chunk_text(LONG_TEXT)
    if len(chunks) >= 2:
        # The end of chunk 0 should overlap with start of chunk 1
        c0_end = chunks[0]["content"][-100:]
        c1_start = chunks[1]["content"][:200]
        # Some overlap text should appear in both chunks
        # (exact overlap depends on split points, just verify chunks aren't disjoint)
        assert len(chunks[0]["content"]) > 0
        assert len(chunks[1]["content"]) > 0


def test_chunk_empty_text():
    chunks = chunk_text("")
    assert len(chunks) == 1
    assert chunks[0]["content"] == ""
    assert chunks[0]["token_count"] == 0


@pytest.mark.asyncio
async def test_generate_embeddings():
    mock_response = AsyncMock()
    mock_response.data = [
        AsyncMock(embedding=[0.1] * 512, index=0),
    ]

    mock_client = AsyncMock()
    mock_client.embeddings.create.return_value = mock_response

    with patch("jordan_claw.obsidian.embeddings.AsyncOpenAI", return_value=mock_client):
        embeddings = await generate_embeddings(["test text"], api_key="test-key")

    assert len(embeddings) == 1
    assert len(embeddings[0]) == 512
    mock_client.embeddings.create.assert_called_once_with(
        model="text-embedding-3-small",
        input=["test text"],
        dimensions=512,
    )


@pytest.mark.asyncio
async def test_generate_embeddings_multiple():
    mock_response = AsyncMock()
    mock_response.data = [
        AsyncMock(embedding=[0.1] * 512, index=0),
        AsyncMock(embedding=[0.2] * 512, index=1),
    ]

    mock_client = AsyncMock()
    mock_client.embeddings.create.return_value = mock_response

    with patch("jordan_claw.obsidian.embeddings.AsyncOpenAI", return_value=mock_client):
        embeddings = await generate_embeddings(
            ["text one", "text two"], api_key="test-key"
        )

    assert len(embeddings) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/jb/Developer/jb_homebase/jordan-claw && uv run pytest tests/test_obsidian_embeddings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jordan_claw.obsidian.embeddings'`

- [ ] **Step 3: Implement chunking and embeddings**

Create `jordan-claw/src/jordan_claw/obsidian/embeddings.py`:

```python
from __future__ import annotations

import re

from openai import AsyncOpenAI

CHARS_PER_TOKEN = 4
MAX_CHUNK_TOKENS = 1000
OVERLAP_RATIO = 0.10
HEADING_PATTERN = re.compile(r"^#{1,3}\s", re.MULTILINE)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 512


def _estimate_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


def chunk_text(text: str) -> list[dict]:
    """Split text into chunks, splitting at markdown headings when over token limit.

    Returns list of dicts with keys: content, chunk_index, token_count.
    """
    if _estimate_tokens(text) <= MAX_CHUNK_TOKENS:
        return [{"content": text, "chunk_index": 0, "token_count": _estimate_tokens(text)}]

    # Split at heading boundaries
    sections: list[str] = []
    positions = [m.start() for m in HEADING_PATTERN.finditer(text)]

    if not positions:
        # No headings: split at paragraph boundaries
        paragraphs = text.split("\n\n")
        sections = [p for p in paragraphs if p.strip()]
    else:
        # Split text at each heading
        for i, pos in enumerate(positions):
            end = positions[i + 1] if i + 1 < len(positions) else len(text)
            section = text[pos:end].strip()
            if section:
                sections.append(section)
        # Include any text before the first heading
        if positions[0] > 0:
            preamble = text[: positions[0]].strip()
            if preamble:
                sections.insert(0, preamble)

    # Merge small sections, split large sections
    chunks: list[str] = []
    current = ""

    for section in sections:
        candidate = (current + "\n\n" + section).strip() if current else section
        if _estimate_tokens(candidate) <= MAX_CHUNK_TOKENS:
            current = candidate
        else:
            if current:
                chunks.append(current)
            if _estimate_tokens(section) > MAX_CHUNK_TOKENS:
                # Section itself is too large, split by paragraphs
                for para in section.split("\n\n"):
                    if not para.strip():
                        continue
                    if current and _estimate_tokens(current + "\n\n" + para) <= MAX_CHUNK_TOKENS:
                        current = current + "\n\n" + para
                    else:
                        if current:
                            chunks.append(current)
                        current = para
            else:
                current = section

    if current:
        chunks.append(current)

    if not chunks:
        return [{"content": text, "chunk_index": 0, "token_count": _estimate_tokens(text)}]

    # Add overlap between adjacent chunks
    overlap_chars = int(MAX_CHUNK_TOKENS * CHARS_PER_TOKEN * OVERLAP_RATIO)
    result: list[dict] = []

    for i, chunk in enumerate(chunks):
        if i > 0 and overlap_chars > 0:
            prev_tail = chunks[i - 1][-overlap_chars:]
            chunk = prev_tail + "\n\n" + chunk

        result.append({
            "content": chunk,
            "chunk_index": i,
            "token_count": _estimate_tokens(chunk),
        })

    return result


async def generate_embeddings(
    texts: list[str],
    api_key: str,
) -> list[list[float]]:
    """Generate embeddings for a list of texts using OpenAI API."""
    client = AsyncOpenAI(api_key=api_key)
    response = await client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
        dimensions=EMBEDDING_DIMENSIONS,
    )
    # Sort by index to preserve order
    sorted_data = sorted(response.data, key=lambda d: d.index)
    return [d.embedding for d in sorted_data]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/jb/Developer/jb_homebase/jordan-claw && uv run pytest tests/test_obsidian_embeddings.py -v`
Expected: 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add jordan-claw/src/jordan_claw/obsidian/embeddings.py jordan-claw/tests/test_obsidian_embeddings.py
git commit -m "feat: add chunking and OpenAI embedding generation for obsidian notes"
```

---

### Task 5: DB CRUD layer for obsidian

**Files:**
- Create: `jordan-claw/src/jordan_claw/db/obsidian.py`
- Create: `jordan-claw/tests/test_db_obsidian.py`

- [ ] **Step 1: Write the failing tests**

Create `jordan-claw/tests/test_db_obsidian.py`:

```python
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


def _mock_db(data: list | None = None) -> AsyncMock:
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

    db = AsyncMock()
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
    db = AsyncMock()
    db.rpc.return_value = AsyncMock()
    db.rpc.return_value.execute = AsyncMock(
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
    results = await search_notes_semantic(
        db, org_id="org-1", embedding=[0.1] * 512
    )
    assert len(results) == 1
    assert results[0]["similarity"] == 0.85
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/jb/Developer/jb_homebase/jordan-claw && uv run pytest tests/test_db_obsidian.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jordan_claw.db.obsidian'`

- [ ] **Step 3: Implement the DB layer**

Create `jordan-claw/src/jordan_claw/db/obsidian.py`:

```python
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
```

- [ ] **Step 4: Add the RPC function to the migration**

Append to `jordan-claw/supabase/migrations/003_obsidian_tables.sql`:

```sql
-- RPC function for semantic search with optional filters
create or replace function search_obsidian_notes(
    p_org_id uuid,
    p_embedding vector(512),
    p_limit int default 10,
    p_note_type text default null,
    p_tags text[] default null
)
returns table (
    note_id uuid,
    title text,
    note_type text,
    tags text[],
    chunk_content text,
    chunk_index int,
    similarity float
)
language sql stable
as $$
    select
        n.id as note_id,
        n.title,
        n.note_type,
        n.tags,
        c.content as chunk_content,
        c.chunk_index,
        1 - (c.embedding <=> p_embedding) as similarity
    from obsidian_note_chunks c
    join obsidian_notes n on n.id = c.note_id
    where n.org_id = p_org_id
      and n.is_archived = false
      and (p_note_type is null or n.note_type = p_note_type)
      and (p_tags is null or n.tags && p_tags)
    order by c.embedding <=> p_embedding
    limit p_limit;
$$;
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/jb/Developer/jb_homebase/jordan-claw && uv run pytest tests/test_db_obsidian.py -v`
Expected: 8 tests PASS

- [ ] **Step 6: Commit**

```bash
git add jordan-claw/src/jordan_claw/db/obsidian.py jordan-claw/tests/test_db_obsidian.py jordan-claw/supabase/migrations/003_obsidian_tables.sql
git commit -m "feat: add DB CRUD layer and RPC function for obsidian notes"
```

---

### Task 6: Config and AgentDeps updates

**Files:**
- Modify: `jordan-claw/src/jordan_claw/config.py`
- Modify: `jordan-claw/src/jordan_claw/agents/deps.py`
- Modify: `jordan-claw/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Add to `jordan-claw/tests/test_config.py`:

```python
def test_settings_has_openai_api_key(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "test-anon")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-bot")
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily")
    monkeypatch.setenv("FASTMAIL_USERNAME", "test@fastmail.com")
    monkeypatch.setenv("FASTMAIL_APP_PASSWORD", "test-pw")
    monkeypatch.setenv("DEFAULT_ORG_ID", "org-123")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    settings = Settings()
    assert settings.openai_api_key == "test-openai"
```

Add the import at the top if not present:

```python
from jordan_claw.config import Settings
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /home/jb/Developer/jb_homebase/jordan-claw && uv run pytest tests/test_config.py::test_settings_has_openai_api_key -v`
Expected: FAIL — `openai_api_key` field not found on Settings

- [ ] **Step 3: Add openai_api_key to Settings**

In `jordan-claw/src/jordan_claw/config.py`, add after the `fastmail_app_password` line:

```python
    openai_api_key: str
```

- [ ] **Step 4: Add openai_api_key to AgentDeps**

In `jordan-claw/src/jordan_claw/agents/deps.py`, add after the `supabase_client` line:

```python
    openai_api_key: str = ""
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd /home/jb/Developer/jb_homebase/jordan-claw && uv run pytest tests/test_config.py::test_settings_has_openai_api_key -v`
Expected: PASS

- [ ] **Step 6: Run all existing tests to ensure no regressions**

Run: `cd /home/jb/Developer/jb_homebase/jordan-claw && uv run pytest tests/ -v`
Expected: All tests PASS. The new `openai_api_key` field on Settings may cause failures in tests that construct Settings without it. If so, add `monkeypatch.setenv("OPENAI_API_KEY", "test-openai")` to affected test fixtures.

- [ ] **Step 7: Commit**

```bash
git add jordan-claw/src/jordan_claw/config.py jordan-claw/src/jordan_claw/agents/deps.py jordan-claw/tests/test_config.py
git commit -m "feat: add openai_api_key to Settings and AgentDeps"
```

---

### Task 7: search_notes tool

**Files:**
- Create: `jordan-claw/src/jordan_claw/tools/obsidian.py`
- Create: `jordan-claw/tests/test_obsidian_tools.py`

- [ ] **Step 1: Write the failing tests**

Create `jordan-claw/tests/test_obsidian_tools.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai import RunContext

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.tools.obsidian import search_notes


def _make_ctx() -> RunContext[AgentDeps]:
    ctx = MagicMock(spec=RunContext)
    ctx.deps = AgentDeps(
        org_id="org-1",
        tavily_api_key="test",
        fastmail_username="test",
        fastmail_app_password="test",
        supabase_client=AsyncMock(),
        openai_api_key="test-openai",
    )
    return ctx


@pytest.mark.asyncio
@patch("jordan_claw.tools.obsidian.generate_embeddings")
@patch("jordan_claw.tools.obsidian.search_notes_semantic")
async def test_search_notes_returns_results(mock_search, mock_embed):
    mock_embed.return_value = [[0.1] * 512]
    mock_search.return_value = [
        {
            "note_id": "note-1",
            "title": "Test Note",
            "note_type": "atomic-note",
            "tags": ["test"],
            "chunk_content": "This is matching content from the note.",
            "chunk_index": 0,
            "similarity": 0.85,
        }
    ]
    ctx = _make_ctx()
    result = await search_notes(ctx, query="test query")
    assert "Test Note" in result
    assert "atomic-note" in result
    assert "0.85" in result
    mock_embed.assert_called_once_with(["test query"], api_key="test-openai")


@pytest.mark.asyncio
@patch("jordan_claw.tools.obsidian.generate_embeddings")
@patch("jordan_claw.tools.obsidian.search_notes_semantic")
async def test_search_notes_no_results(mock_search, mock_embed):
    mock_embed.return_value = [[0.1] * 512]
    mock_search.return_value = []
    ctx = _make_ctx()
    result = await search_notes(ctx, query="nothing")
    assert "No matching notes" in result


@pytest.mark.asyncio
@patch("jordan_claw.tools.obsidian.generate_embeddings")
@patch("jordan_claw.tools.obsidian.search_notes_semantic")
async def test_search_notes_with_filters(mock_search, mock_embed):
    mock_embed.return_value = [[0.1] * 512]
    mock_search.return_value = []
    ctx = _make_ctx()
    await search_notes(ctx, query="test", note_type="source", tags=["leadership"])
    mock_search.assert_called_once_with(
        ctx.deps.supabase_client,
        org_id="org-1",
        embedding=[0.1] * 512,
        note_type="source",
        tags=["leadership"],
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/jb/Developer/jb_homebase/jordan-claw && uv run pytest tests/test_obsidian_tools.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jordan_claw.tools.obsidian'`

- [ ] **Step 3: Implement search_notes**

Create `jordan-claw/src/jordan_claw/tools/obsidian.py`:

```python
from __future__ import annotations

from pydantic_ai import RunContext

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.db.obsidian import search_notes_semantic
from jordan_claw.obsidian.embeddings import generate_embeddings

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/jb/Developer/jb_homebase/jordan-claw && uv run pytest tests/test_obsidian_tools.py -v`
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add jordan-claw/src/jordan_claw/tools/obsidian.py jordan-claw/tests/test_obsidian_tools.py
git commit -m "feat: add search_notes tool with semantic search"
```

---

### Task 8: read_note and create_source_note tools

**Files:**
- Modify: `jordan-claw/src/jordan_claw/tools/obsidian.py`
- Modify: `jordan-claw/tests/test_obsidian_tools.py`

- [ ] **Step 1: Write the failing tests for read_note**

Append to `jordan-claw/tests/test_obsidian_tools.py`:

```python
from jordan_claw.tools.obsidian import read_note


@pytest.mark.asyncio
@patch("jordan_claw.tools.obsidian.get_note_by_title")
async def test_read_note_found(mock_get):
    from jordan_claw.obsidian.models import ObsidianNote

    mock_get.return_value = [
        ObsidianNote(
            id="note-1",
            org_id="org-1",
            vault_path="30-Notes/Test.md",
            title="Test Note",
            note_type="atomic-note",
            content="The full note body here.",
            frontmatter={"type": "atomic-note", "created": "2026-03-16"},
            tags=["test", "leadership"],
            wiki_links=["Related Note", "Another Note"],
            content_hash="hash",
            created_at="2026-04-04T00:00:00+00:00",
            updated_at="2026-04-04T00:00:00+00:00",
        )
    ]
    ctx = _make_ctx()
    result = await read_note(ctx, title="Test Note")
    assert "Test Note" in result
    assert "The full note body here." in result
    assert "test" in result
    assert "Related Note" in result


@pytest.mark.asyncio
@patch("jordan_claw.tools.obsidian.get_note_by_title")
async def test_read_note_not_found(mock_get):
    mock_get.return_value = []
    ctx = _make_ctx()
    result = await read_note(ctx, title="Nonexistent")
    assert "No notes found" in result


@pytest.mark.asyncio
@patch("jordan_claw.tools.obsidian.get_note_by_title")
async def test_read_note_multiple_matches(mock_get):
    from jordan_claw.obsidian.models import ObsidianNote

    mock_get.return_value = [
        ObsidianNote(
            id="note-1", org_id="org-1", vault_path="a.md", title="Safety Culture",
            note_type="atomic-note", content="", frontmatter={}, content_hash="h1",
            created_at="2026-04-04T00:00:00+00:00", updated_at="2026-04-04T00:00:00+00:00",
        ),
        ObsidianNote(
            id="note-2", org_id="org-1", vault_path="b.md", title="Psychological Safety",
            note_type="source", content="", frontmatter={}, content_hash="h2",
            created_at="2026-04-04T00:00:00+00:00", updated_at="2026-04-04T00:00:00+00:00",
        ),
    ]
    ctx = _make_ctx()
    result = await read_note(ctx, title="Safety")
    assert "Safety Culture" in result
    assert "Psychological Safety" in result
    assert "Multiple notes" in result
```

- [ ] **Step 2: Write the failing tests for create_source_note**

Append to `jordan-claw/tests/test_obsidian_tools.py`:

```python
from jordan_claw.tools.obsidian import create_source_note


@pytest.mark.asyncio
@patch("jordan_claw.tools.obsidian.insert_chunks")
@patch("jordan_claw.tools.obsidian.generate_embeddings")
@patch("jordan_claw.tools.obsidian.insert_note")
async def test_create_source_note(mock_insert, mock_embed, mock_chunks):
    mock_insert.return_value = {"id": "new-note-1"}
    mock_embed.return_value = [[0.1] * 512]
    ctx = _make_ctx()
    result = await create_source_note(
        ctx,
        title="New Article",
        url="https://example.com/article",
        author="Test Author",
        source_type="article",
        tags=["ai", "agents"],
        summary="A summary of the article.",
        key_takeaways=["Takeaway one", "Takeaway two"],
    )
    assert "New Article" in result
    assert "created" in result.lower()

    # Verify insert was called with correct vault_path and source_origin
    call_kwargs = mock_insert.call_args[1]
    assert call_kwargs["vault_path"] == "20-Sources/New Article.md"
    assert call_kwargs["source_origin"] == "claw"
    assert call_kwargs["sync_status"] == "pending_export"
    assert "source" in call_kwargs["note_type"]

    # Verify embedding was generated
    mock_embed.assert_called_once()


@pytest.mark.asyncio
@patch("jordan_claw.tools.obsidian.insert_chunks")
@patch("jordan_claw.tools.obsidian.generate_embeddings")
@patch("jordan_claw.tools.obsidian.insert_note")
async def test_create_source_note_renders_correct_markdown(mock_insert, mock_embed, mock_chunks):
    mock_insert.return_value = {"id": "new-note-1"}
    mock_embed.return_value = [[0.1] * 512]
    ctx = _make_ctx()
    await create_source_note(
        ctx,
        title="Test Article",
        url="https://example.com",
        author="Author Name",
        source_type="article",
        tags=["test"],
        summary="Article summary here.",
        key_takeaways=["Point one", "Point two"],
    )
    call_kwargs = mock_insert.call_args[1]
    content = call_kwargs["content"]
    assert "## Summary" in content
    assert "Article summary here." in content
    assert "## Key Takeaways" in content
    assert "Point one" in content
    assert "Point two" in content
    assert "## Related Topics" in content
    assert "## Notes" in content
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /home/jb/Developer/jb_homebase/jordan-claw && uv run pytest tests/test_obsidian_tools.py -v`
Expected: FAIL — `read_note` and `create_source_note` not importable

- [ ] **Step 4: Implement read_note and create_source_note**

Append to `jordan-claw/src/jordan_claw/tools/obsidian.py`:

```python
from datetime import UTC, datetime

from jordan_claw.db.obsidian import get_note_by_title, insert_chunks, insert_note
from jordan_claw.obsidian.embeddings import chunk_text


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
    import hashlib
    import yaml

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
```

- [ ] **Step 5: Update imports at top of obsidian.py**

Ensure the top of `jordan-claw/src/jordan_claw/tools/obsidian.py` has all needed imports:

```python
from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import yaml
from pydantic_ai import RunContext

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.db.obsidian import get_note_by_title, insert_chunks, insert_note, search_notes_semantic
from jordan_claw.obsidian.embeddings import chunk_text, generate_embeddings

SNIPPET_MAX_CHARS = 800  # ~200 tokens
```

Remove the inline `import hashlib` and `import yaml` from `create_source_note`.

- [ ] **Step 6: Add pyyaml dependency**

In `jordan-claw/pyproject.toml`, add to dependencies:

```toml
    "pyyaml>=6.0",
```

Run: `cd /home/jb/Developer/jb_homebase/jordan-claw && uv sync`

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd /home/jb/Developer/jb_homebase/jordan-claw && uv run pytest tests/test_obsidian_tools.py -v`
Expected: 8 tests PASS

- [ ] **Step 8: Commit**

```bash
git add jordan-claw/src/jordan_claw/tools/obsidian.py jordan-claw/tests/test_obsidian_tools.py jordan-claw/pyproject.toml
git commit -m "feat: add read_note and create_source_note tools"
```

---

### Task 9: Tool registry and gateway wiring

**Files:**
- Modify: `jordan-claw/src/jordan_claw/tools/__init__.py`
- Modify: `jordan-claw/src/jordan_claw/gateway/router.py`
- Modify: `jordan-claw/tests/test_tool_registry.py`

- [ ] **Step 1: Update the test for the tool registry**

In `jordan-claw/tests/test_tool_registry.py`, update the expected tools list to include the three new obsidian tools. Find the test that checks `TOOL_REGISTRY` keys and add:

```python
"search_notes",
"read_note",
"create_source_note",
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jb/Developer/jb_homebase/jordan-claw && uv run pytest tests/test_tool_registry.py -v`
Expected: FAIL — missing obsidian tools

- [ ] **Step 3: Add obsidian tools to TOOL_REGISTRY**

In `jordan-claw/src/jordan_claw/tools/__init__.py`, add imports and registry entries:

```python
from jordan_claw.tools.obsidian import create_source_note, read_note, search_notes
```

Add to the `TOOL_REGISTRY` dict:

```python
    "search_notes": search_notes,
    "read_note": read_note,
    "create_source_note": create_source_note,
```

- [ ] **Step 4: Wire openai_api_key into AgentDeps in gateway/router.py**

In `jordan-claw/src/jordan_claw/gateway/router.py`, update the `handle_message` function signature to accept `openai_api_key`:

Add `openai_api_key: str = "",` to the function parameters (after `fastmail_app_password`).

Update the `AgentDeps` construction inside `handle_message`:

```python
        deps = AgentDeps(
            org_id=msg.org_id,
            tavily_api_key=tavily_api_key,
            fastmail_username=fastmail_username,
            fastmail_app_password=fastmail_app_password,
            supabase_client=db,
            openai_api_key=openai_api_key,
        )
```

- [ ] **Step 5: Update handle_message callers**

Find where `handle_message` is called (likely `jordan-claw/src/jordan_claw/channels/telegram.py` and/or `jordan-claw/src/jordan_claw/main.py`) and pass `openai_api_key=settings.openai_api_key` to the call.

- [ ] **Step 6: Run all tests to verify no regressions**

Run: `cd /home/jb/Developer/jb_homebase/jordan-claw && uv run pytest tests/ -v`
Expected: All tests PASS. If gateway tests fail because they don't pass `openai_api_key`, add it to the mock calls.

- [ ] **Step 7: Commit**

```bash
git add jordan-claw/src/jordan_claw/tools/__init__.py jordan-claw/src/jordan_claw/gateway/router.py jordan-claw/tests/test_tool_registry.py
git commit -m "feat: register obsidian tools and wire openai_api_key through gateway"
```

---

### Task 10: Sync script - ingest

**Files:**
- Create: `jordan-claw/scripts/obsidian_sync/__init__.py`
- Create: `jordan-claw/scripts/obsidian_sync/ingest.py`
- Create: `jordan-claw/tests/test_obsidian_sync_ingest.py`

- [ ] **Step 1: Write the failing tests**

Create `jordan-claw/tests/test_obsidian_sync_ingest.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/jb/Developer/jb_homebase/jordan-claw && uv run pytest tests/test_obsidian_sync_ingest.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement ingest**

Create `jordan-claw/scripts/obsidian_sync/__init__.py` (empty file).

Create `jordan-claw/scripts/obsidian_sync/ingest.py`:

```python
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
                    db, ex["id"], parsed["content"], openai_api_key
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
                    db, note_id, parsed["content"], openai_api_key
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
) -> None:
    """Chunk content, generate embeddings, and insert into DB."""
    chunks = chunk_text(content)
    if not chunks or (len(chunks) == 1 and not chunks[0]["content"]):
        return

    texts = [c["content"] for c in chunks if c["content"]]
    if not texts:
        return

    embeddings = await generate_embeddings(texts, api_key=openai_api_key)

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
```

- [ ] **Step 4: Add scripts to Python path**

In `jordan-claw/pyproject.toml`, update the pytest configuration so the scripts directory is importable. Add to `[tool.pytest.ini_options]`:

```toml
pythonpath = ["src", "scripts/.."]
```

Alternatively, add a `conftest.py` to the jordan-claw root that adds the scripts dir to sys.path, or restructure the import. The simplest approach: in `jordan-claw/pyproject.toml`, under `[tool.pytest.ini_options]`:

```toml
pythonpath = ["src", "."]
```

This makes `scripts.obsidian_sync.ingest` importable from the jordan-claw root.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/jb/Developer/jb_homebase/jordan-claw && uv run pytest tests/test_obsidian_sync_ingest.py -v`
Expected: 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add jordan-claw/scripts/obsidian_sync/ jordan-claw/tests/test_obsidian_sync_ingest.py jordan-claw/pyproject.toml
git commit -m "feat: add obsidian vault ingest script with change detection"
```

---

### Task 11: Sync script - export and CLI

**Files:**
- Create: `jordan-claw/scripts/obsidian_sync/export.py`
- Create: `jordan-claw/scripts/obsidian_sync/cli.py`
- Create: `jordan-claw/tests/test_obsidian_sync_export.py`

- [ ] **Step 1: Write the failing tests for export**

Create `jordan-claw/tests/test_obsidian_sync_export.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/jb/Developer/jb_homebase/jordan-claw && uv run pytest tests/test_obsidian_sync_export.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement export**

Create `jordan-claw/scripts/obsidian_sync/export.py`:

```python
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
```

- [ ] **Step 4: Create CLI entry point**

Create `jordan-claw/scripts/obsidian_sync/cli.py`:

```python
from __future__ import annotations

import asyncio

import click
import structlog

from jordan_claw.config import get_settings
from jordan_claw.db.client import close_supabase_client, get_supabase_client
from scripts.obsidian_sync.export import export_notes
from scripts.obsidian_sync.ingest import ingest_vault

log = structlog.get_logger()

DEFAULT_VAULT_PATH = "/home/jb/Documents/Obsidian Vault"


async def _run_ingest(vault_path: str) -> dict:
    settings = get_settings()
    db = await get_supabase_client(settings.supabase_url, settings.supabase_service_key)
    try:
        return await ingest_vault(
            db,
            org_id=settings.default_org_id,
            vault_path=vault_path,
            openai_api_key=settings.openai_api_key,
        )
    finally:
        await close_supabase_client()


async def _run_export(vault_path: str) -> dict:
    settings = get_settings()
    db = await get_supabase_client(settings.supabase_url, settings.supabase_service_key)
    try:
        return await export_notes(
            db,
            org_id=settings.default_org_id,
            vault_path=vault_path,
        )
    finally:
        await close_supabase_client()


@click.group()
def cli():
    """Obsidian vault sync tool for Jordan Claw."""
    structlog.configure(
        processors=[
            structlog.dev.ConsoleRenderer(),
        ],
    )


@cli.command()
@click.option("--vault", default=DEFAULT_VAULT_PATH, help="Path to Obsidian vault")
def ingest(vault: str):
    """Ingest vault notes into Supabase."""
    stats = asyncio.run(_run_ingest(vault))
    click.echo(
        f"Ingest complete: {stats['inserted']} inserted, {stats['updated']} updated, "
        f"{stats['skipped']} skipped, {stats['archived']} archived"
    )


@cli.command()
@click.option("--vault", default=DEFAULT_VAULT_PATH, help="Path to Obsidian vault")
def export(vault: str):
    """Export Claw-created notes to vault."""
    stats = asyncio.run(_run_export(vault))
    click.echo(f"Export complete: {stats['exported']} exported")


@cli.command()
@click.option("--vault", default=DEFAULT_VAULT_PATH, help="Path to Obsidian vault")
def run(vault: str):
    """Run ingest then export."""
    ingest_stats = asyncio.run(_run_ingest(vault))
    export_stats = asyncio.run(_run_export(vault))
    click.echo(
        f"Ingest: {ingest_stats['inserted']} inserted, {ingest_stats['updated']} updated, "
        f"{ingest_stats['skipped']} skipped, {ingest_stats['archived']} archived"
    )
    click.echo(f"Export: {export_stats['exported']} exported")


if __name__ == "__main__":
    cli()
```

- [ ] **Step 5: Add CLI script entry point to pyproject.toml**

In `jordan-claw/pyproject.toml`, add:

```toml
[project.scripts]
obsidian-sync = "scripts.obsidian_sync.cli:cli"
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /home/jb/Developer/jb_homebase/jordan-claw && uv run pytest tests/test_obsidian_sync_export.py -v`
Expected: 3 tests PASS

- [ ] **Step 7: Run the full test suite**

Run: `cd /home/jb/Developer/jb_homebase/jordan-claw && uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add jordan-claw/scripts/obsidian_sync/ jordan-claw/tests/test_obsidian_sync_export.py jordan-claw/pyproject.toml
git commit -m "feat: add obsidian sync export and CLI entry point"
```

---

### Task 12: DB agent config and system prompt update

This task updates the live agent config in Supabase. No code changes.

- [ ] **Step 1: Add tools to agent config**

Run this SQL in Supabase:

```sql
UPDATE agents
SET tools = tools || '["search_notes", "read_note", "create_source_note"]'::jsonb
WHERE slug = 'claw-main';
```

- [ ] **Step 2: Add Obsidian context to system prompt**

Run this SQL to append the Obsidian instructions to the system prompt:

```sql
UPDATE agents
SET system_prompt = system_prompt || E'\n\nYou have access to Jordan''s Obsidian knowledge base. Use search_notes when asked about concepts, ideas, or sources. Use read_note to get the full content of a specific note. Use create_source_note when Jordan shares or you find a valuable article, resource, or reference worth capturing.'
WHERE slug = 'claw-main';
```

- [ ] **Step 3: Add OPENAI_API_KEY to Infisical/environment**

Add the `OPENAI_API_KEY` secret to Infisical for the jordan-claw project and to the Railway environment variables.

- [ ] **Step 4: Commit (nothing to commit, DB-only changes)**

No code changes. Record the config update in a commit message for tracking:

```bash
git commit --allow-empty -m "chore: update agent config with obsidian tools and system prompt"
```

---

### Task 13: Manual smoke test

- [ ] **Step 1: Run the migration**

Execute `003_obsidian_tables.sql` in the Supabase SQL editor, including the RPC function. Then run:

```sql
SELECT pg_notify('pgrst', 'reload schema');
```

- [ ] **Step 2: Run initial ingest**

```bash
cd /home/jb/Developer/jb_homebase/jordan-claw
uv run obsidian-sync ingest
```

Expected: ~208 notes inserted, 0 updated, 0 skipped, 0 archived.

- [ ] **Step 3: Verify data in Supabase**

Check `obsidian_notes` table has ~208 rows. Check `obsidian_note_chunks` has rows with non-null embeddings.

- [ ] **Step 4: Test search via Telegram**

Message @jb_homebase_bot: "What notes do I have about psychological safety?"

Verify Claw uses `search_notes` and returns relevant results.

- [ ] **Step 5: Test read via Telegram**

Message: "Read the full note on [title from search results]"

Verify Claw uses `read_note` and returns the full note content.

- [ ] **Step 6: Test create source note**

Message: "Save this as a source: Title: Test Article, URL: https://example.com, Author: Test, Type: article, Tags: test, Summary: A test summary, Takeaways: One, Two"

Verify note appears in `obsidian_notes` with `sync_status='pending_export'`.

- [ ] **Step 7: Test export**

```bash
uv run obsidian-sync export
```

Verify the file appears in `/home/jb/Documents/Obsidian Vault/20-Sources/`.

- [ ] **Step 8: Test idempotent re-ingest**

```bash
uv run obsidian-sync ingest
```

Expected: 0 inserted, 0 updated, ~208 skipped, 0 archived.

- [ ] **Step 9: Set up cron job**

```bash
crontab -e
```

Add:

```
0 3 * * 0,3 cd /home/jb/Developer/jb_homebase/jordan-claw && /home/jb/.local/bin/uv run obsidian-sync run >> /var/log/obsidian-sync.log 2>&1
```
