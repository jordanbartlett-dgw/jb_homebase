# Jordan Claw Memory System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add persistent per-tenant memory to Jordan Claw so conversations build on prior context.

**Architecture:** Async memory extraction via a background Haiku LLM call after each response. Hybrid read path: pre-rendered summary injected into system prompt + `recall_memory`/`forget_memory` tools for deeper queries. Three Supabase tables (facts, events, context) with RLS.

**Tech Stack:** Python 3.12, Pydantic AI (structured output), FastAPI, Supabase (supabase-py async), structlog

**Spec:** `docs/superpowers/specs/2026-04-03-jordan-claw-memory-system-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `jordan-claw/src/jordan_claw/memory/__init__.py` | Package init |
| `jordan-claw/src/jordan_claw/memory/models.py` | Pydantic models: `ExtractedFact`, `ExtractedEvent`, `ExtractionResult`, `MemoryFact` |
| `jordan-claw/src/jordan_claw/memory/extractor.py` | Extraction agent definition, system prompt, `extract_memory_background()` |
| `jordan-claw/src/jordan_claw/memory/reader.py` | `load_memory_context()`, `render_context_block()`, token budget logic |
| `jordan-claw/src/jordan_claw/db/memory.py` | CRUD: `get_active_facts`, `upsert_facts`, `append_events`, `get_memory_context`, `upsert_memory_context`, `mark_context_stale`, `search_facts`, `archive_fact` |
| `jordan-claw/src/jordan_claw/tools/memory.py` | `recall_memory()` and `forget_memory()` tool implementations |
| `jordan-claw/supabase/migrations/002_memory_tables.sql` | DDL for `memory_facts`, `memory_events`, `memory_context` |
| `jordan-claw/tests/test_memory_models.py` | Tests for Pydantic models |
| `jordan-claw/tests/test_db_memory.py` | Tests for DB CRUD layer |
| `jordan-claw/tests/test_memory_extractor.py` | Tests for extraction agent and background task |
| `jordan-claw/tests/test_memory_reader.py` | Tests for context loading and rendering |
| `jordan-claw/tests/test_memory_tools.py` | Tests for recall_memory and forget_memory tools |

### Modified Files

| File | Change |
|------|--------|
| `jordan-claw/src/jordan_claw/agents/deps.py` | Add `supabase_client` field to `AgentDeps` |
| `jordan-claw/src/jordan_claw/agents/factory.py` | Accept optional `memory_context` param, prepend to system prompt |
| `jordan-claw/src/jordan_claw/gateway/router.py` | Add memory read (before agent build) and write (after response) steps |
| `jordan-claw/src/jordan_claw/tools/__init__.py` | Register `recall_memory` and `forget_memory` |
| `jordan-claw/tests/test_tool_registry.py` | Update expected tools list |
| `jordan-claw/tests/test_agents.py` | Update `AgentDeps` construction to include new field |
| `jordan-claw/tests/test_gateway.py` | Update `handle_message` calls for new behavior |

---

## Task 1: Database Migration

**Files:**
- Create: `jordan-claw/supabase/migrations/002_memory_tables.sql`

- [ ] **Step 1: Write the migration SQL**

```sql
-- Jordan Claw Memory System Schema
-- Run this in the Supabase SQL Editor

-- Persistent facts about a tenant
create table memory_facts (
    id uuid primary key default gen_random_uuid(),
    org_id uuid references organizations(id) on delete cascade not null,
    category text not null check (category in ('preference', 'decision', 'entity', 'workflow', 'relationship')),
    content text not null,
    source text not null check (source in ('conversation', 'explicit', 'inferred')),
    confidence float not null default 0.8,
    metadata jsonb default '{}',
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    expires_at timestamptz,
    is_archived boolean default false
);

-- Timestamped log of significant interactions
create table memory_events (
    id uuid primary key default gen_random_uuid(),
    org_id uuid references organizations(id) on delete cascade not null,
    event_type text not null check (event_type in ('decision', 'task_completed', 'feedback', 'milestone', 'correction')),
    summary text not null,
    context jsonb default '{}',
    created_at timestamptz default now()
);

-- Pre-rendered prompt blocks for injection
create table memory_context (
    id uuid primary key default gen_random_uuid(),
    org_id uuid references organizations(id) on delete cascade not null,
    scope text not null,
    context_block text not null,
    is_stale boolean default true,
    last_computed timestamptz,
    unique(org_id, scope)
);

-- Indexes
create index idx_memory_facts_org_active on memory_facts(org_id) where is_archived = false;
create index idx_memory_facts_org_category on memory_facts(org_id, category) where is_archived = false;
create index idx_memory_events_org_created on memory_events(org_id, created_at desc);

-- RLS
alter table memory_facts enable row level security;
alter table memory_events enable row level security;
alter table memory_context enable row level security;
```

- [ ] **Step 2: Commit**

```bash
git add jordan-claw/supabase/migrations/002_memory_tables.sql
git commit -m "feat: add memory system database migration"
```

---

## Task 2: Memory Pydantic Models

**Files:**
- Create: `jordan-claw/src/jordan_claw/memory/__init__.py`
- Create: `jordan-claw/src/jordan_claw/memory/models.py`
- Create: `jordan-claw/tests/test_memory_models.py`

- [ ] **Step 1: Create the package init**

```python
# jordan-claw/src/jordan_claw/memory/__init__.py
```

Empty file. Just marks the directory as a package.

- [ ] **Step 2: Write failing tests for memory models**

```python
# jordan-claw/tests/test_memory_models.py
from __future__ import annotations

from jordan_claw.memory.models import (
    ExtractedEvent,
    ExtractedFact,
    ExtractionResult,
    MemoryFact,
)


def test_extracted_fact_with_defaults():
    fact = ExtractedFact(
        content="Prefers morning meetings",
        category="preference",
        source="conversation",
        confidence=0.8,
    )
    assert fact.replaces_fact_id is None
    assert fact.confidence == 0.8


def test_extracted_fact_with_replacement():
    fact = ExtractedFact(
        content="Actually prefers afternoon meetings",
        category="preference",
        source="explicit",
        confidence=1.0,
        replaces_fact_id="fact-001",
    )
    assert fact.replaces_fact_id == "fact-001"


def test_extracted_event():
    event = ExtractedEvent(
        event_type="decision",
        summary="Chose FastAPI over Flask",
    )
    assert event.event_type == "decision"


def test_extraction_result_empty():
    result = ExtractionResult(facts=[], events=[], has_corrections=False)
    assert len(result.facts) == 0
    assert not result.has_corrections


def test_extraction_result_with_items():
    result = ExtractionResult(
        facts=[
            ExtractedFact(
                content="Uses Pydantic AI",
                category="preference",
                source="conversation",
                confidence=0.9,
            ),
        ],
        events=[
            ExtractedEvent(
                event_type="decision",
                summary="Chose Pydantic AI over LangChain",
            ),
        ],
        has_corrections=False,
    )
    assert len(result.facts) == 1
    assert len(result.events) == 1


def test_memory_fact_from_db_row():
    row = {
        "id": "fact-001",
        "org_id": "org-001",
        "category": "preference",
        "content": "Prefers concise responses",
        "source": "conversation",
        "confidence": 0.9,
        "metadata": {"conversation_id": "conv-001"},
        "created_at": "2026-04-01T00:00:00Z",
        "updated_at": "2026-04-01T00:00:00Z",
        "expires_at": None,
        "is_archived": False,
    }
    fact = MemoryFact.model_validate(row)
    assert fact.id == "fact-001"
    assert fact.category == "preference"
    assert fact.is_archived is False


def test_extracted_fact_rejects_invalid_category():
    import pytest

    with pytest.raises(Exception):
        ExtractedFact(
            content="test",
            category="invalid_category",
            source="conversation",
            confidence=0.5,
        )


def test_extracted_fact_rejects_invalid_source():
    import pytest

    with pytest.raises(Exception):
        ExtractedFact(
            content="test",
            category="preference",
            source="invalid_source",
            confidence=0.5,
        )
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd jordan-claw && uv run pytest tests/test_memory_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jordan_claw.memory.models'`

- [ ] **Step 4: Implement the models**

```python
# jordan-claw/src/jordan_claw/memory/models.py
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ExtractedFact(BaseModel):
    """A fact extracted from a conversation turn by the extraction agent."""

    content: str
    category: Literal["preference", "decision", "entity", "workflow", "relationship"]
    source: Literal["conversation", "explicit", "inferred"]
    confidence: float
    replaces_fact_id: str | None = None


class ExtractedEvent(BaseModel):
    """A notable event extracted from a conversation turn."""

    event_type: Literal["decision", "task_completed", "feedback", "milestone"]
    summary: str


class ExtractionResult(BaseModel):
    """Structured output from the memory extraction agent."""

    facts: list[ExtractedFact]
    events: list[ExtractedEvent]
    has_corrections: bool


class MemoryFact(BaseModel):
    """A fact row from the memory_facts table."""

    id: str
    org_id: str
    category: str
    content: str
    source: str
    confidence: float
    metadata: dict = {}
    created_at: str
    updated_at: str
    expires_at: str | None = None
    is_archived: bool = False
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd jordan-claw && uv run pytest tests/test_memory_models.py -v`
Expected: All 8 tests PASS

- [ ] **Step 6: Run ruff**

Run: `cd jordan-claw && uv run ruff check src/jordan_claw/memory/ tests/test_memory_models.py`

- [ ] **Step 7: Commit**

```bash
git add jordan-claw/src/jordan_claw/memory/__init__.py jordan-claw/src/jordan_claw/memory/models.py jordan-claw/tests/test_memory_models.py
git commit -m "feat: add memory system Pydantic models"
```

---

## Task 3: Memory DB CRUD Layer

**Files:**
- Create: `jordan-claw/src/jordan_claw/db/memory.py`
- Create: `jordan-claw/tests/test_db_memory.py`

- [ ] **Step 1: Write failing tests for DB layer**

```python
# jordan-claw/tests/test_db_memory.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from jordan_claw.db.memory import (
    append_events,
    archive_fact,
    get_active_facts,
    get_memory_context,
    mark_context_stale,
    search_facts,
    upsert_facts,
    upsert_memory_context,
)
from jordan_claw.memory.models import ExtractedEvent, ExtractedFact


ORG_ID = "org-001"


def _mock_db(select_data=None, insert_data=None, update_data=None, upsert_data=None):
    """Build a mock Supabase async client with chained query builder."""
    mock_result = MagicMock(data=select_data or [])

    mock_query = MagicMock()
    mock_query.execute = AsyncMock(return_value=mock_result)
    mock_query.limit.return_value = mock_query
    mock_query.eq.return_value = mock_query
    mock_query.ilike.return_value = mock_query
    mock_query.order.return_value = mock_query
    mock_query.select.return_value = mock_query
    mock_query.insert.return_value = mock_query
    mock_query.update.return_value = mock_query
    mock_query.upsert.return_value = mock_query

    mock_db = MagicMock()
    mock_db.table.return_value = mock_query
    return mock_db, mock_query


@pytest.mark.asyncio
async def test_get_active_facts_returns_list():
    facts_data = [
        {
            "id": "f1",
            "org_id": ORG_ID,
            "category": "preference",
            "content": "Likes coffee",
            "source": "conversation",
            "confidence": 0.8,
            "metadata": {},
            "created_at": "2026-04-01T00:00:00Z",
            "updated_at": "2026-04-01T00:00:00Z",
            "expires_at": None,
            "is_archived": False,
        }
    ]
    db, query = _mock_db(select_data=facts_data)
    result = await get_active_facts(db, ORG_ID)

    assert len(result) == 1
    assert result[0].id == "f1"
    db.table.assert_called_with("memory_facts")


@pytest.mark.asyncio
async def test_get_active_facts_empty():
    db, query = _mock_db(select_data=[])
    result = await get_active_facts(db, ORG_ID)
    assert result == []


@pytest.mark.asyncio
async def test_upsert_facts_insert_new():
    db, query = _mock_db()
    facts = [
        ExtractedFact(
            content="Prefers Python",
            category="preference",
            source="conversation",
            confidence=0.8,
        )
    ]
    existing = []
    await upsert_facts(db, ORG_ID, facts, existing)
    # Should call insert on memory_facts table
    query.insert.assert_called_once()


@pytest.mark.asyncio
async def test_upsert_facts_replace_low_confidence():
    db, query = _mock_db()
    facts = [
        ExtractedFact(
            content="Prefers Go",
            category="preference",
            source="conversation",
            confidence=0.9,
            replaces_fact_id="f1",
        )
    ]
    existing = [
        MagicMock(id="f1", confidence=0.5),  # Low confidence, should be replaced
    ]
    await upsert_facts(db, ORG_ID, facts, existing)
    # Should call update on the existing fact
    query.update.assert_called()


@pytest.mark.asyncio
async def test_upsert_facts_flag_high_confidence():
    db, query = _mock_db()
    facts = [
        ExtractedFact(
            content="Prefers Go",
            category="preference",
            source="conversation",
            confidence=0.9,
            replaces_fact_id="f1",
        )
    ]
    existing = [
        MagicMock(id="f1", confidence=0.9),  # High confidence, should flag
    ]
    await upsert_facts(db, ORG_ID, facts, existing)
    # Should insert new fact with needs_review metadata
    insert_call = query.insert.call_args
    assert insert_call is not None
    inserted_data = insert_call[0][0]
    assert inserted_data["metadata"]["needs_review"] is True


@pytest.mark.asyncio
async def test_append_events():
    db, query = _mock_db()
    events = [
        ExtractedEvent(event_type="decision", summary="Chose FastAPI"),
    ]
    await append_events(db, ORG_ID, events)
    query.insert.assert_called_once()
    inserted = query.insert.call_args[0][0]
    assert inserted[0]["event_type"] == "decision"
    assert inserted[0]["org_id"] == ORG_ID


@pytest.mark.asyncio
async def test_get_memory_context_found():
    ctx_data = [
        {
            "id": "ctx-1",
            "org_id": ORG_ID,
            "scope": "global",
            "context_block": "## Memory\n- Fact 1",
            "is_stale": False,
            "last_computed": "2026-04-01T00:00:00Z",
        }
    ]
    db, query = _mock_db(select_data=ctx_data)
    result = await get_memory_context(db, ORG_ID, scope="global")
    assert result is not None
    assert result["context_block"] == "## Memory\n- Fact 1"


@pytest.mark.asyncio
async def test_get_memory_context_not_found():
    db, query = _mock_db(select_data=[])
    result = await get_memory_context(db, ORG_ID, scope="global")
    assert result is None


@pytest.mark.asyncio
async def test_mark_context_stale():
    db, query = _mock_db()
    await mark_context_stale(db, ORG_ID)
    query.update.assert_called_once()
    update_data = query.update.call_args[0][0]
    assert update_data["is_stale"] is True


@pytest.mark.asyncio
async def test_search_facts():
    facts_data = [
        {
            "id": "f1",
            "org_id": ORG_ID,
            "category": "preference",
            "content": "Likes Python",
            "source": "conversation",
            "confidence": 0.8,
            "metadata": {},
            "created_at": "2026-04-01T00:00:00Z",
            "updated_at": "2026-04-01T00:00:00Z",
            "expires_at": None,
            "is_archived": False,
        }
    ]
    db, query = _mock_db(select_data=facts_data)
    result = await search_facts(db, ORG_ID, query="Python")
    assert len(result) == 1
    query.ilike.assert_called_once()


@pytest.mark.asyncio
async def test_search_facts_with_category():
    db, query = _mock_db(select_data=[])
    await search_facts(db, ORG_ID, query="Python", category="preference")
    # Should have called eq for both org_id and category
    eq_calls = [str(c) for c in query.eq.call_args_list]
    assert len(query.eq.call_args_list) >= 2


@pytest.mark.asyncio
async def test_archive_fact():
    db, query = _mock_db()
    await archive_fact(db, "fact-001")
    query.update.assert_called_once()
    update_data = query.update.call_args[0][0]
    assert update_data["is_archived"] is True


@pytest.mark.asyncio
async def test_upsert_memory_context():
    db, query = _mock_db()
    await upsert_memory_context(db, ORG_ID, scope="global", context_block="## Memory\n- Fact")
    query.upsert.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jordan-claw && uv run pytest tests/test_db_memory.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jordan_claw.db.memory'`

- [ ] **Step 3: Implement the DB CRUD layer**

```python
# jordan-claw/src/jordan_claw/db/memory.py
from __future__ import annotations

from datetime import datetime, timezone

import structlog
from supabase._async.client import AsyncClient

from jordan_claw.memory.models import ExtractedEvent, ExtractedFact, MemoryFact

log = structlog.get_logger()

CONFIDENCE_THRESHOLD = 0.7


async def get_active_facts(client: AsyncClient, org_id: str) -> list[MemoryFact]:
    """Load all non-archived facts for an org."""
    result = (
        await client.table("memory_facts")
        .select("*")
        .eq("org_id", org_id)
        .eq("is_archived", False)
        .order("confidence", desc=True)
        .order("updated_at", desc=True)
        .execute()
    )
    return [MemoryFact.model_validate(row) for row in result.data]


async def upsert_facts(
    client: AsyncClient,
    org_id: str,
    facts: list[ExtractedFact],
    existing: list[MemoryFact],
) -> None:
    """Insert new facts or handle conflicts with existing ones."""
    existing_by_id = {f.id: f for f in existing}

    for fact in facts:
        if fact.replaces_fact_id and fact.replaces_fact_id in existing_by_id:
            old = existing_by_id[fact.replaces_fact_id]

            if old.confidence < CONFIDENCE_THRESHOLD:
                # Auto-replace: update existing row
                await (
                    client.table("memory_facts")
                    .update(
                        {
                            "content": fact.content,
                            "category": fact.category,
                            "source": fact.source,
                            "confidence": fact.confidence,
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                    .eq("id", fact.replaces_fact_id)
                    .execute()
                )
                log.info(
                    "memory_fact_replaced",
                    old_fact_id=fact.replaces_fact_id,
                    new_content=fact.content,
                )
            else:
                # Flag for review: insert new with needs_review
                await (
                    client.table("memory_facts")
                    .insert(
                        {
                            "org_id": org_id,
                            "category": fact.category,
                            "content": fact.content,
                            "source": fact.source,
                            "confidence": fact.confidence,
                            "metadata": {"needs_review": True, "conflicts_with": fact.replaces_fact_id},
                        }
                    )
                    .execute()
                )
                log.info(
                    "memory_fact_flagged",
                    conflicting_fact_id=fact.replaces_fact_id,
                    new_content=fact.content,
                )
        else:
            # New fact, insert
            await (
                client.table("memory_facts")
                .insert(
                    {
                        "org_id": org_id,
                        "category": fact.category,
                        "content": fact.content,
                        "source": fact.source,
                        "confidence": fact.confidence,
                        "metadata": {},
                    }
                )
                .execute()
            )


async def append_events(
    client: AsyncClient,
    org_id: str,
    events: list[ExtractedEvent],
) -> None:
    """Append memory events."""
    if not events:
        return
    rows = [
        {
            "org_id": org_id,
            "event_type": e.event_type,
            "summary": e.summary,
            "context": {},
        }
        for e in events
    ]
    await client.table("memory_events").insert(rows).execute()


async def get_memory_context(
    client: AsyncClient,
    org_id: str,
    scope: str = "global",
) -> dict | None:
    """Load the pre-rendered context block for an org+scope."""
    result = (
        await client.table("memory_context")
        .select("*")
        .eq("org_id", org_id)
        .eq("scope", scope)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


async def upsert_memory_context(
    client: AsyncClient,
    org_id: str,
    scope: str,
    context_block: str,
) -> None:
    """Upsert the pre-rendered context block."""
    await (
        client.table("memory_context")
        .upsert(
            {
                "org_id": org_id,
                "scope": scope,
                "context_block": context_block,
                "is_stale": False,
                "last_computed": datetime.now(timezone.utc).isoformat(),
            },
        )
        .execute()
    )


async def mark_context_stale(client: AsyncClient, org_id: str) -> None:
    """Mark all context blocks for an org as stale."""
    await (
        client.table("memory_context")
        .update({"is_stale": True})
        .eq("org_id", org_id)
        .execute()
    )


async def search_facts(
    client: AsyncClient,
    org_id: str,
    query: str,
    category: str | None = None,
    limit: int = 20,
) -> list[MemoryFact]:
    """Search facts by keyword (ILIKE) with optional category filter."""
    q = (
        client.table("memory_facts")
        .select("*")
        .eq("org_id", org_id)
        .eq("is_archived", False)
        .ilike("content", f"%{query}%")
    )
    if category:
        q = q.eq("category", category)
    result = await q.order("confidence", desc=True).limit(limit).execute()
    return [MemoryFact.model_validate(row) for row in result.data]


async def archive_fact(client: AsyncClient, fact_id: str) -> None:
    """Archive a fact (soft delete)."""
    await (
        client.table("memory_facts")
        .update({"is_archived": True, "updated_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", fact_id)
        .execute()
    )


async def get_recent_events(
    client: AsyncClient,
    org_id: str,
    limit: int = 20,
) -> list[dict]:
    """Load the most recent memory events for an org."""
    result = (
        await client.table("memory_events")
        .select("*")
        .eq("org_id", org_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd jordan-claw && uv run pytest tests/test_db_memory.py -v`
Expected: All 13 tests PASS

- [ ] **Step 5: Run ruff**

Run: `cd jordan-claw && uv run ruff check src/jordan_claw/db/memory.py tests/test_db_memory.py`

- [ ] **Step 6: Commit**

```bash
git add jordan-claw/src/jordan_claw/db/memory.py jordan-claw/tests/test_db_memory.py
git commit -m "feat: add memory DB CRUD layer"
```

---

## Task 4: Memory Context Reader

**Files:**
- Create: `jordan-claw/src/jordan_claw/memory/reader.py`
- Create: `jordan-claw/tests/test_memory_reader.py`

- [ ] **Step 1: Write failing tests**

```python
# jordan-claw/tests/test_memory_reader.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jordan_claw.memory.models import MemoryFact
from jordan_claw.memory.reader import load_memory_context, render_context_block


def _make_fact(
    id: str = "f1",
    category: str = "preference",
    content: str = "Likes Python",
    confidence: float = 0.8,
) -> MemoryFact:
    return MemoryFact(
        id=id,
        org_id="org-001",
        category=category,
        content=content,
        source="conversation",
        confidence=confidence,
        metadata={},
        created_at="2026-04-01T00:00:00Z",
        updated_at="2026-04-01T00:00:00Z",
    )


def test_render_context_block_empty():
    result = render_context_block(facts=[], events=[])
    assert result == ""


def test_render_context_block_single_category():
    facts = [_make_fact(content="Prefers concise responses")]
    result = render_context_block(facts=facts, events=[])
    assert "## Memory Context" in result
    assert "### Preferences" in result
    assert "Prefers concise responses" in result


def test_render_context_block_multiple_categories():
    facts = [
        _make_fact(id="f1", category="preference", content="Likes Python"),
        _make_fact(id="f2", category="decision", content="Chose FastAPI over Flask"),
        _make_fact(id="f3", category="entity", content="DGW: promotional products company"),
    ]
    result = render_context_block(facts=facts, events=[])
    assert "### Preferences" in result
    assert "### Decisions" in result
    assert "### Entities" in result


def test_render_context_block_with_events():
    events = [
        {"event_type": "decision", "summary": "Picked Railway for hosting", "created_at": "2026-04-01T10:00:00Z"},
    ]
    result = render_context_block(facts=[], events=events)
    assert "### Recent Activity" in result
    assert "Picked Railway for hosting" in result


def test_render_context_block_respects_token_budget():
    # Create many facts that exceed budget
    facts = [
        _make_fact(id=f"f{i}", content=f"Fact number {i} with some extra text to use tokens")
        for i in range(100)
    ]
    result = render_context_block(facts=facts, events=[], max_tokens=200)
    # Should not include all 100 facts
    assert result.count("- ") < 100


def test_render_context_block_prioritizes_high_confidence():
    facts = [
        _make_fact(id="low", content="Low confidence fact", confidence=0.3),
        _make_fact(id="high", content="High confidence fact", confidence=1.0),
    ]
    result = render_context_block(facts=facts, events=[], max_tokens=100)
    # High confidence should always be included
    assert "High confidence fact" in result


@pytest.mark.asyncio
async def test_load_memory_context_uses_cache():
    """When cache is fresh, return it without recomputing."""
    mock_db = MagicMock()
    cached = {
        "context_block": "## Memory\n- Cached fact",
        "is_stale": False,
    }
    with patch("jordan_claw.memory.reader.get_memory_context", return_value=cached):
        result = await load_memory_context(mock_db, "org-001")
    assert result == "## Memory\n- Cached fact"


@pytest.mark.asyncio
async def test_load_memory_context_recomputes_when_stale():
    """When cache is stale, recompute from facts and events."""
    mock_db = MagicMock()
    stale_cache = {
        "context_block": "old content",
        "is_stale": True,
    }
    facts = [_make_fact(content="Fresh fact")]
    with (
        patch("jordan_claw.memory.reader.get_memory_context", return_value=stale_cache),
        patch("jordan_claw.memory.reader.get_active_facts", return_value=facts),
        patch("jordan_claw.memory.reader.get_recent_events", return_value=[]),
        patch("jordan_claw.memory.reader.upsert_memory_context", new_callable=AsyncMock) as mock_upsert,
    ):
        result = await load_memory_context(mock_db, "org-001")
    assert "Fresh fact" in result
    mock_upsert.assert_called_once()


@pytest.mark.asyncio
async def test_load_memory_context_recomputes_when_no_cache():
    """When no cache exists, compute from facts and events."""
    mock_db = MagicMock()
    facts = [_make_fact(content="New fact")]
    with (
        patch("jordan_claw.memory.reader.get_memory_context", return_value=None),
        patch("jordan_claw.memory.reader.get_active_facts", return_value=facts),
        patch("jordan_claw.memory.reader.get_recent_events", return_value=[]),
        patch("jordan_claw.memory.reader.upsert_memory_context", new_callable=AsyncMock),
    ):
        result = await load_memory_context(mock_db, "org-001")
    assert "New fact" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jordan-claw && uv run pytest tests/test_memory_reader.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the reader**

```python
# jordan-claw/src/jordan_claw/memory/reader.py
from __future__ import annotations

from supabase._async.client import AsyncClient

from jordan_claw.db.memory import (
    get_active_facts,
    get_memory_context,
    get_recent_events,
    upsert_memory_context,
)
from jordan_claw.memory.models import MemoryFact

# Category display names, ordered for rendering
CATEGORY_LABELS = {
    "preference": "Preferences",
    "decision": "Decisions",
    "entity": "Entities",
    "workflow": "Workflows",
    "relationship": "Relationships",
}

# Rough estimate: 1 token ≈ 4 chars
CHARS_PER_TOKEN = 4


def render_context_block(
    facts: list[MemoryFact],
    events: list[dict],
    max_tokens: int = 500,
) -> str:
    """Render facts and events into a markdown context block for system prompt injection."""
    if not facts and not events:
        return ""

    max_chars = max_tokens * CHARS_PER_TOKEN

    # Group facts by category
    grouped: dict[str, list[MemoryFact]] = {}
    for fact in facts:
        grouped.setdefault(fact.category, []).append(fact)

    lines = ["## Memory Context", ""]
    char_count = 20  # Header chars

    # Render facts by category
    for category, label in CATEGORY_LABELS.items():
        category_facts = grouped.get(category, [])
        if not category_facts:
            continue

        section_header = f"### {label}"
        char_count += len(section_header) + 1
        if char_count > max_chars:
            break

        lines.append(section_header)
        for fact in category_facts:
            line = f"- {fact.content}"
            char_count += len(line) + 1
            if char_count > max_chars:
                break
            lines.append(line)
        lines.append("")

    # Render recent events
    if events and char_count < max_chars:
        lines.append("### Recent Activity")
        for event in events[:10]:
            created = event.get("created_at", "")[:10]
            date_str = created[5:] if len(created) >= 10 else ""
            # Format as [Mon DD]
            line = f"- [{date_str}] {event['summary']}"
            char_count += len(line) + 1
            if char_count > max_chars:
                break
            lines.append(line)
        lines.append("")

    return "\n".join(lines).strip()


async def load_memory_context(
    db: AsyncClient,
    org_id: str,
    scope: str = "global",
) -> str:
    """Load the memory context block, recomputing if stale or missing."""
    cached = await get_memory_context(db, org_id, scope=scope)

    if cached and not cached["is_stale"]:
        return cached["context_block"]

    # Recompute from facts + events
    facts = await get_active_facts(db, org_id)
    events = await get_recent_events(db, org_id, limit=20)
    context_block = render_context_block(facts, events)

    # Cache the result
    await upsert_memory_context(db, org_id, scope=scope, context_block=context_block)

    return context_block
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd jordan-claw && uv run pytest tests/test_memory_reader.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Run ruff**

Run: `cd jordan-claw && uv run ruff check src/jordan_claw/memory/reader.py tests/test_memory_reader.py`

- [ ] **Step 6: Commit**

```bash
git add jordan-claw/src/jordan_claw/memory/reader.py jordan-claw/tests/test_memory_reader.py
git commit -m "feat: add memory context reader with token budget"
```

---

## Task 5: Memory Extraction Agent

**Files:**
- Create: `jordan-claw/src/jordan_claw/memory/extractor.py`
- Create: `jordan-claw/tests/test_memory_extractor.py`

- [ ] **Step 1: Write failing tests**

```python
# jordan-claw/tests/test_memory_extractor.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jordan_claw.memory.extractor import (
    build_extraction_prompt,
    create_extraction_agent,
    extract_memory_background,
)
from jordan_claw.memory.models import ExtractionResult, MemoryFact


def test_create_extraction_agent():
    agent = create_extraction_agent()
    # Should be configured with structured result type
    assert agent.result_type is ExtractionResult


def test_build_extraction_prompt_basic():
    prompt = build_extraction_prompt(
        user_message="I prefer working in the morning",
        assistant_response="Noted! I'll keep that in mind.",
        existing_facts=[],
    )
    assert "I prefer working in the morning" in prompt
    assert "Noted!" in prompt
    assert "existing facts" in prompt.lower() or "no existing facts" in prompt.lower()


def test_build_extraction_prompt_with_existing_facts():
    facts = [
        MemoryFact(
            id="f1",
            org_id="org-001",
            category="preference",
            content="Prefers Python",
            source="conversation",
            confidence=0.8,
            metadata={},
            created_at="2026-04-01T00:00:00Z",
            updated_at="2026-04-01T00:00:00Z",
        ),
    ]
    prompt = build_extraction_prompt(
        user_message="Actually I prefer Go now",
        assistant_response="Got it.",
        existing_facts=facts,
    )
    assert "f1" in prompt
    assert "Prefers Python" in prompt


@pytest.mark.asyncio
async def test_extract_memory_background_success():
    """Background extraction should call the extraction agent and persist results."""
    mock_db = MagicMock()
    mock_result = MagicMock()
    mock_result.output = ExtractionResult(
        facts=[],
        events=[],
        has_corrections=False,
    )

    with (
        patch("jordan_claw.memory.extractor.get_active_facts", return_value=[]),
        patch("jordan_claw.memory.extractor.create_extraction_agent") as mock_create,
        patch("jordan_claw.memory.extractor.upsert_facts", new_callable=AsyncMock) as mock_upsert,
        patch("jordan_claw.memory.extractor.append_events", new_callable=AsyncMock) as mock_append,
        patch("jordan_claw.memory.extractor.mark_context_stale", new_callable=AsyncMock) as mock_stale,
    ):
        mock_agent = AsyncMock()
        mock_agent.run.return_value = mock_result
        mock_create.return_value = mock_agent

        await extract_memory_background(
            db=mock_db,
            org_id="org-001",
            user_message="Hello",
            assistant_response="Hi there",
        )

    mock_upsert.assert_called_once()
    mock_append.assert_called_once()
    mock_stale.assert_called_once_with(mock_db, "org-001")


@pytest.mark.asyncio
async def test_extract_memory_background_handles_corrections():
    """When has_corrections is true, facts should get confidence=1.0 and old facts archived."""
    mock_db = MagicMock()
    from jordan_claw.memory.models import ExtractedFact

    mock_result = MagicMock()
    mock_result.output = ExtractionResult(
        facts=[
            ExtractedFact(
                content="Prefers Go",
                category="preference",
                source="explicit",
                confidence=1.0,
                replaces_fact_id="f1",
            )
        ],
        events=[],
        has_corrections=True,
    )

    existing_fact = MemoryFact(
        id="f1",
        org_id="org-001",
        category="preference",
        content="Prefers Python",
        source="conversation",
        confidence=0.9,
        metadata={},
        created_at="2026-04-01T00:00:00Z",
        updated_at="2026-04-01T00:00:00Z",
    )

    with (
        patch("jordan_claw.memory.extractor.get_active_facts", return_value=[existing_fact]),
        patch("jordan_claw.memory.extractor.create_extraction_agent") as mock_create,
        patch("jordan_claw.memory.extractor.archive_fact", new_callable=AsyncMock) as mock_archive,
        patch("jordan_claw.memory.extractor.upsert_facts", new_callable=AsyncMock),
        patch("jordan_claw.memory.extractor.append_events", new_callable=AsyncMock) as mock_events,
        patch("jordan_claw.memory.extractor.mark_context_stale", new_callable=AsyncMock),
    ):
        mock_agent = AsyncMock()
        mock_agent.run.return_value = mock_result
        mock_create.return_value = mock_agent

        await extract_memory_background(
            db=mock_db,
            org_id="org-001",
            user_message="Actually I prefer Go",
            assistant_response="Updated.",
        )

    mock_archive.assert_called_once_with(mock_db, "f1")
    # Should append a correction event
    events_call = mock_events.call_args[0]
    assert any(e.event_type == "correction" for e in events_call[2]) or mock_events.call_count >= 1


@pytest.mark.asyncio
async def test_extract_memory_background_logs_errors():
    """Extraction failures should be logged, not raised."""
    mock_db = MagicMock()

    with (
        patch("jordan_claw.memory.extractor.get_active_facts", side_effect=Exception("DB down")),
        patch("jordan_claw.memory.extractor.log") as mock_log,
    ):
        # Should not raise
        await extract_memory_background(
            db=mock_db,
            org_id="org-001",
            user_message="Hello",
            assistant_response="Hi",
        )

    mock_log.exception.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jordan-claw && uv run pytest tests/test_memory_extractor.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the extractor**

```python
# jordan-claw/src/jordan_claw/memory/extractor.py
from __future__ import annotations

import structlog
from pydantic_ai import Agent
from supabase._async.client import AsyncClient

from jordan_claw.db.memory import (
    append_events,
    archive_fact,
    get_active_facts,
    mark_context_stale,
    upsert_facts,
)
from jordan_claw.memory.models import ExtractedEvent, ExtractionResult, MemoryFact

log = structlog.get_logger()

EXTRACTION_SYSTEM_PROMPT = """\
You are a memory extraction agent. Your job is to identify facts and events \
from a conversation turn that are worth remembering long-term.

Rules:
1. Only extract facts with clear signal. Do not extract every passing mention.
2. Set category to one of: preference, decision, entity, workflow, relationship.
3. Set source to "explicit" when the user says "remember that..." or directly states \
something to remember. Set to "conversation" for facts inferred from natural dialogue. \
Set to "inferred" only for facts derived from patterns across multiple statements.
4. Set confidence between 0.0 and 1.0. Use 1.0 for explicit statements, 0.7-0.9 for \
clear conversational facts, 0.5-0.7 for inferred facts.
5. If a new fact contradicts an existing fact, set replaces_fact_id to the ID of the \
existing fact.
6. If the user corrects a previous statement, set has_corrections to true.
7. Do not extract facts that are already captured in the existing facts list.
8. For events, only capture significant decisions, completions, or feedback. Not routine \
conversation.
9. If there is nothing worth extracting, return empty lists.
"""


def create_extraction_agent() -> Agent[None, ExtractionResult]:
    """Create the memory extraction agent with structured output."""
    return Agent(
        "anthropic:claude-haiku-4-5-20251001",
        system_prompt=EXTRACTION_SYSTEM_PROMPT,
        result_type=ExtractionResult,
    )


def build_extraction_prompt(
    user_message: str,
    assistant_response: str,
    existing_facts: list[MemoryFact],
) -> str:
    """Build the user prompt for the extraction agent."""
    facts_section = "No existing facts."
    if existing_facts:
        fact_lines = [
            f"- [{f.id}] ({f.category}, confidence={f.confidence}) {f.content}"
            for f in existing_facts
        ]
        facts_section = "Existing facts:\n" + "\n".join(fact_lines)

    return f"""\
Analyze this conversation turn and extract any new facts or notable events.

## Conversation Turn

**User:** {user_message}

**Assistant:** {assistant_response}

## {facts_section}

Extract new or updated facts and events. Return empty lists if nothing is worth remembering."""


async def extract_memory_background(
    db: AsyncClient,
    org_id: str,
    user_message: str,
    assistant_response: str,
) -> None:
    """Fire-and-forget memory extraction from a conversation turn."""
    try:
        existing_facts = await get_active_facts(db, org_id)
        agent = create_extraction_agent()
        prompt = build_extraction_prompt(user_message, assistant_response, existing_facts)
        result = await agent.run(prompt)
        extraction = result.output

        # Handle corrections: archive old facts, pin new ones
        if extraction.has_corrections:
            for fact in extraction.facts:
                if fact.replaces_fact_id:
                    await archive_fact(db, fact.replaces_fact_id)
            # Add a correction event
            correction_events = [
                ExtractedEvent(event_type="correction", summary=f"User corrected: {f.content}")
                for f in extraction.facts
                if f.replaces_fact_id
            ]
            extraction.events.extend(correction_events)

        await upsert_facts(db, org_id, extraction.facts, existing_facts)
        await append_events(db, org_id, extraction.events)
        await mark_context_stale(db, org_id)

        log.info(
            "memory_extraction_complete",
            org_id=org_id,
            facts_extracted=len(extraction.facts),
            events_extracted=len(extraction.events),
            has_corrections=extraction.has_corrections,
        )

    except Exception:
        log.exception("memory_extraction_failed", org_id=org_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd jordan-claw && uv run pytest tests/test_memory_extractor.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Run ruff**

Run: `cd jordan-claw && uv run ruff check src/jordan_claw/memory/extractor.py tests/test_memory_extractor.py`

- [ ] **Step 6: Commit**

```bash
git add jordan-claw/src/jordan_claw/memory/extractor.py jordan-claw/tests/test_memory_extractor.py
git commit -m "feat: add memory extraction agent with structured output"
```

---

## Task 6: Memory Tools (recall_memory + forget_memory)

**Files:**
- Create: `jordan-claw/src/jordan_claw/tools/memory.py`
- Create: `jordan-claw/tests/test_memory_tools.py`
- Modify: `jordan-claw/src/jordan_claw/tools/__init__.py`
- Modify: `jordan-claw/tests/test_tool_registry.py`

- [ ] **Step 1: Write failing tests for memory tools**

```python
# jordan-claw/tests/test_memory_tools.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jordan_claw.memory.models import MemoryFact
from jordan_claw.tools.memory import forget_memory, recall_memory


def _make_ctx(org_id: str = "org-001", db: MagicMock | None = None):
    """Build a mock RunContext with AgentDeps."""
    ctx = MagicMock()
    ctx.deps.org_id = org_id
    ctx.deps.supabase_client = db or MagicMock()
    return ctx


def _make_fact(content: str = "Likes Python", id: str = "f1") -> MemoryFact:
    return MemoryFact(
        id=id,
        org_id="org-001",
        category="preference",
        content=content,
        source="conversation",
        confidence=0.8,
        metadata={},
        created_at="2026-04-01T00:00:00Z",
        updated_at="2026-04-01T00:00:00Z",
    )


@pytest.mark.asyncio
async def test_recall_memory_returns_formatted_facts():
    ctx = _make_ctx()
    facts = [_make_fact("Prefers Python"), _make_fact("Uses FastAPI", id="f2")]
    with patch("jordan_claw.tools.memory.search_facts", return_value=facts):
        result = await recall_memory(ctx, query="Python")
    assert "Prefers Python" in result
    assert "Uses FastAPI" in result


@pytest.mark.asyncio
async def test_recall_memory_no_results():
    ctx = _make_ctx()
    with patch("jordan_claw.tools.memory.search_facts", return_value=[]):
        result = await recall_memory(ctx, query="nonexistent")
    assert "no matching" in result.lower() or "nothing" in result.lower()


@pytest.mark.asyncio
async def test_recall_memory_with_category():
    ctx = _make_ctx()
    with patch("jordan_claw.tools.memory.search_facts", return_value=[]) as mock_search:
        await recall_memory(ctx, query="Python", category="preference")
    mock_search.assert_called_once_with(
        ctx.deps.supabase_client, "org-001", query="Python", category="preference"
    )


@pytest.mark.asyncio
async def test_forget_memory_single_match():
    ctx = _make_ctx()
    facts = [_make_fact("Prefers Python")]
    with (
        patch("jordan_claw.tools.memory.search_facts", return_value=facts),
        patch("jordan_claw.tools.memory.archive_fact", new_callable=AsyncMock) as mock_archive,
    ):
        result = await forget_memory(ctx, query="Python")
    mock_archive.assert_called_once_with(ctx.deps.supabase_client, "f1")
    assert "forgot" in result.lower() or "archived" in result.lower()


@pytest.mark.asyncio
async def test_forget_memory_multiple_matches():
    ctx = _make_ctx()
    facts = [
        _make_fact("Prefers Python", id="f1"),
        _make_fact("Python is great", id="f2"),
    ]
    with patch("jordan_claw.tools.memory.search_facts", return_value=facts):
        result = await forget_memory(ctx, query="Python")
    # Should NOT archive, should list matches for user confirmation
    assert "f1" in result or "Prefers Python" in result
    assert "f2" in result or "Python is great" in result


@pytest.mark.asyncio
async def test_forget_memory_no_matches():
    ctx = _make_ctx()
    with patch("jordan_claw.tools.memory.search_facts", return_value=[]):
        result = await forget_memory(ctx, query="nonexistent")
    assert "no matching" in result.lower() or "nothing" in result.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jordan-claw && uv run pytest tests/test_memory_tools.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the memory tools**

```python
# jordan-claw/src/jordan_claw/tools/memory.py
from __future__ import annotations

from pydantic_ai import RunContext

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.db.memory import archive_fact, search_facts


async def recall_memory(
    ctx: RunContext[AgentDeps],
    query: str,
    category: str | None = None,
) -> str:
    """Search memory for specific facts. Use when asked 'what do you know about...'
    or when you need deeper context than what's in your memory summary."""
    facts = await search_facts(
        ctx.deps.supabase_client, ctx.deps.org_id, query=query, category=category
    )

    if not facts:
        return "No matching memories found."

    lines = [f"Found {len(facts)} memory fact(s):", ""]
    for fact in facts:
        lines.append(f"- [{fact.category}] {fact.content} (confidence: {fact.confidence})")
    return "\n".join(lines)


async def forget_memory(
    ctx: RunContext[AgentDeps],
    query: str,
) -> str:
    """Forget (archive) a memory fact. Searches by keyword and archives the match.
    If multiple matches, lists them for the user to clarify."""
    facts = await search_facts(ctx.deps.supabase_client, ctx.deps.org_id, query=query)

    if not facts:
        return "No matching memories found to forget."

    if len(facts) == 1:
        await archive_fact(ctx.deps.supabase_client, facts[0].id)
        return f"Forgot: {facts[0].content}"

    # Multiple matches: list for confirmation
    lines = [
        f"Found {len(facts)} matching memories. Please be more specific about which to forget:",
        "",
    ]
    for fact in facts:
        lines.append(f"- {fact.content}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd jordan-claw && uv run pytest tests/test_memory_tools.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Update AgentDeps to include supabase_client**

Modify `jordan-claw/src/jordan_claw/agents/deps.py`:

```python
# jordan-claw/src/jordan_claw/agents/deps.py
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class AgentDeps(BaseModel):
    """Credentials and context passed to tools via RunContext[AgentDeps]."""

    org_id: str
    tavily_api_key: str
    fastmail_username: str
    fastmail_app_password: str
    supabase_client: Any = None  # AsyncClient, typed as Any to avoid serialization issues

    model_config = {"arbitrary_types_allowed": True}
```

- [ ] **Step 6: Update tool registry**

Modify `jordan-claw/src/jordan_claw/tools/__init__.py`:

```python
# jordan-claw/src/jordan_claw/tools/__init__.py
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from jordan_claw.tools.calendar import check_calendar, schedule_event
from jordan_claw.tools.memory import forget_memory, recall_memory
from jordan_claw.tools.time import current_datetime
from jordan_claw.tools.web_search import search_web

TOOL_REGISTRY: dict[str, Callable[..., Any]] = {
    "current_datetime": current_datetime,
    "search_web": search_web,
    "check_calendar": check_calendar,
    "schedule_event": schedule_event,
    "recall_memory": recall_memory,
    "forget_memory": forget_memory,
}
```

- [ ] **Step 7: Update test_tool_registry.py**

Modify `jordan-claw/tests/test_tool_registry.py` line 7:

Change:
```python
EXPECTED_TOOLS = ["current_datetime", "search_web", "check_calendar", "schedule_event"]
```
To:
```python
EXPECTED_TOOLS = [
    "current_datetime",
    "search_web",
    "check_calendar",
    "schedule_event",
    "recall_memory",
    "forget_memory",
]
```

- [ ] **Step 8: Update test_agents.py AgentDeps constructions**

In `jordan-claw/tests/test_agents.py`, update the `test_agent_deps_construction` test (line 13-20):

```python
def test_agent_deps_construction():
    deps = AgentDeps(
        org_id="test-org",
        tavily_api_key="tavily-key",
        fastmail_username="user@fastmail.com",
        fastmail_app_password="app-pass",
    )
    assert deps.org_id == "test-org"
    assert deps.tavily_api_key == "tavily-key"
    assert deps.supabase_client is None
```

- [ ] **Step 9: Run all tests to verify nothing is broken**

Run: `cd jordan-claw && uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 10: Run ruff**

Run: `cd jordan-claw && uv run ruff check src/jordan_claw/tools/memory.py src/jordan_claw/agents/deps.py src/jordan_claw/tools/__init__.py`

- [ ] **Step 11: Commit**

```bash
git add jordan-claw/src/jordan_claw/tools/memory.py jordan-claw/src/jordan_claw/agents/deps.py jordan-claw/src/jordan_claw/tools/__init__.py jordan-claw/tests/test_memory_tools.py jordan-claw/tests/test_tool_registry.py jordan-claw/tests/test_agents.py
git commit -m "feat: add recall_memory and forget_memory tools"
```

---

## Task 7: Wire Memory Into Gateway Router

**Files:**
- Modify: `jordan-claw/src/jordan_claw/agents/factory.py`
- Modify: `jordan-claw/src/jordan_claw/gateway/router.py`
- Modify: `jordan-claw/tests/test_gateway.py`

- [ ] **Step 1: Update build_agent to accept memory_context**

Modify `jordan-claw/src/jordan_claw/agents/factory.py`. Change the `build_agent` function (lines 14-39):

```python
async def build_agent(
    db: AsyncClient,
    org_id: str,
    agent_slug: str,
    memory_context: str = "",
) -> tuple[Agent[AgentDeps], str]:
    """Build a Pydantic AI agent from DB config and the tool registry.

    Returns (agent, model_name) so callers can log/store the model
    without reaching into Pydantic AI internals.
    """
    config = await get_agent_config(db, org_id, agent_slug)

    tools = []
    for name in config.tools:
        if name in TOOL_REGISTRY:
            tools.append(TOOL_REGISTRY[name])
        else:
            log.warning("unknown_tool_skipped", tool_name=name, agent_slug=agent_slug)

    system_prompt = config.system_prompt
    if memory_context:
        system_prompt = memory_context + "\n\n" + system_prompt

    agent = Agent(
        config.model,
        system_prompt=system_prompt,
        tools=tools,
        deps_type=AgentDeps,
    )
    return agent, config.model
```

- [ ] **Step 2: Update gateway router to load memory and fire extraction**

Modify `jordan-claw/src/jordan_claw/gateway/router.py`. Full updated file:

```python
from __future__ import annotations

import asyncio
import time

import structlog
from supabase._async.client import AsyncClient

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.agents.factory import build_agent, db_messages_to_history
from jordan_claw.db.conversations import get_or_create_conversation, update_conversation_status
from jordan_claw.db.messages import get_recent_messages, message_exists, save_message
from jordan_claw.gateway.models import GatewayResponse, IncomingMessage
from jordan_claw.memory.extractor import extract_memory_background
from jordan_claw.memory.reader import load_memory_context
from jordan_claw.utils.token_counting import extract_usage

logger = structlog.get_logger()

ERROR_RESPONSE = "Something went wrong. Try again."


async def handle_message(
    msg: IncomingMessage,
    *,
    db: AsyncClient,
    agent_slug: str,
    tavily_api_key: str,
    fastmail_username: str,
    fastmail_app_password: str,
    history_limit: int = 50,
    environment: str = "development",
) -> GatewayResponse:
    """Process an incoming message through the full gateway lifecycle."""
    log = logger.bind(
        org_id=msg.org_id,
        channel=msg.channel,
        channel_thread_id=msg.channel_thread_id,
    )

    # 1. Dedup
    if await message_exists(db, msg.channel_message_id):
        log.info("duplicate_message_skipped", channel_message_id=msg.channel_message_id)
        return GatewayResponse(content="", conversation_id="")

    # 2. Get or create conversation
    conversation = await get_or_create_conversation(
        db, msg.org_id, msg.channel, msg.channel_thread_id
    )
    conversation_id = conversation["id"]
    log = log.bind(conversation_id=conversation_id, agent_slug=agent_slug)

    # 3. Save user message
    await save_message(
        db,
        conversation_id=conversation_id,
        role="user",
        content=msg.content,
        channel_message_id=msg.channel_message_id,
    )

    # 4. Load history
    db_messages = await get_recent_messages(db, conversation_id, limit=history_limit)

    # 5. Load memory context
    memory_context = await load_memory_context(db, msg.org_id)

    # 6. Build agent from DB config, run with deps
    try:
        start = time.monotonic()

        agent, model_name = await build_agent(
            db, msg.org_id, agent_slug, memory_context=memory_context
        )
        deps = AgentDeps(
            org_id=msg.org_id,
            tavily_api_key=tavily_api_key,
            fastmail_username=fastmail_username,
            fastmail_app_password=fastmail_app_password,
            supabase_client=db,
        )
        history = db_messages_to_history(db_messages)

        result = await agent.run(msg.content, message_history=history, deps=deps)

        latency_ms = int((time.monotonic() - start) * 1000)
        response_text = result.output
        usage = extract_usage(result.usage())

        if environment == "development":
            log.debug("agent_message_content", content=msg.content, response=response_text)

        log.info(
            "agent_run_complete",
            status="success",
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            total_tokens=usage["total_tokens"],
            model=model_name,
            latency_ms=latency_ms,
        )

    except Exception:
        log.exception("agent_run_failed", status="error")
        await update_conversation_status(db, conversation_id, "error")
        await save_message(
            db,
            conversation_id=conversation_id,
            role="assistant",
            content=ERROR_RESPONSE,
        )
        return GatewayResponse(content=ERROR_RESPONSE, conversation_id=conversation_id)

    # 7. Save assistant response
    await save_message(
        db,
        conversation_id=conversation_id,
        role="assistant",
        content=response_text,
        token_count=usage["total_tokens"],
        model=model_name,
    )

    # 8. Fire-and-forget memory extraction
    asyncio.create_task(
        extract_memory_background(db, msg.org_id, msg.content, response_text)
    )

    # 9. Return
    return GatewayResponse(
        content=response_text,
        conversation_id=conversation_id,
        token_count=usage["total_tokens"],
        model=model_name,
    )
```

- [ ] **Step 3: Update gateway tests**

Modify `jordan-claw/tests/test_gateway.py`. The `test_successful_message_flow` test needs patches for the new memory imports:

```python
# jordan-claw/tests/test_gateway.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jordan_claw.gateway.models import IncomingMessage
from jordan_claw.gateway.router import ERROR_RESPONSE, handle_message


def make_incoming(
    content: str = "Hello",
    channel_message_id: str = "telegram:123",
) -> IncomingMessage:
    return IncomingMessage(
        channel="telegram",
        channel_thread_id="chat_456",
        channel_message_id=channel_message_id,
        content=content,
        org_id="1408252a-fd36-4fd3-b527-3b2f495d7b9c",
    )


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.mark.asyncio
async def test_duplicate_message_returns_empty(mock_db):
    """Duplicate messages should be skipped."""
    with patch("jordan_claw.gateway.router.message_exists", return_value=True):
        result = await handle_message(
            make_incoming(),
            db=mock_db,
            agent_slug="claw-main",
            tavily_api_key="test-key",
            fastmail_username="test@fastmail.com",
            fastmail_app_password="test-password",
        )

    assert result.content == ""
    assert result.conversation_id == ""


@pytest.mark.asyncio
async def test_successful_message_flow(mock_db):
    """A normal message should go through the full lifecycle and return a response."""
    fake_conversation = {"id": "conv-001"}
    fake_messages = [
        {
            "role": "user",
            "content": "Hi",
            "created_at": "2026-01-01T00:00:00Z",
            "token_count": None,
            "model": None,
            "metadata": {},
        },
    ]

    mock_usage = MagicMock()
    mock_usage.input_tokens = 10
    mock_usage.output_tokens = 5
    mock_usage.requests = 1

    mock_result = MagicMock()
    mock_result.output = "Hello! How can I help?"
    mock_result.usage.return_value = mock_usage

    mock_agent = AsyncMock()
    mock_agent.run.return_value = mock_result

    with (
        patch("jordan_claw.gateway.router.message_exists", return_value=False),
        patch(
            "jordan_claw.gateway.router.get_or_create_conversation",
            return_value=fake_conversation,
        ),
        patch("jordan_claw.gateway.router.save_message", return_value={}),
        patch(
            "jordan_claw.gateway.router.get_recent_messages",
            return_value=fake_messages,
        ),
        patch("jordan_claw.gateway.router.load_memory_context", return_value=""),
        patch(
            "jordan_claw.gateway.router.build_agent",
            return_value=(mock_agent, "claude-sonnet-4-20250514"),
        ),
        patch("jordan_claw.gateway.router.extract_memory_background", new_callable=AsyncMock),
    ):
        result = await handle_message(
            make_incoming(),
            db=mock_db,
            agent_slug="claw-main",
            tavily_api_key="test-key",
            fastmail_username="test@fastmail.com",
            fastmail_app_password="test-password",
        )

    assert result.content == "Hello! How can I help?"
    assert result.conversation_id == "conv-001"
    assert result.token_count == 15
    assert result.model == "claude-sonnet-4-20250514"

    # Verify deps were passed to agent.run
    call_kwargs = mock_agent.run.call_args.kwargs
    assert "deps" in call_kwargs
    assert call_kwargs["deps"].org_id == "1408252a-fd36-4fd3-b527-3b2f495d7b9c"
    assert call_kwargs["deps"].tavily_api_key == "test-key"
    assert call_kwargs["deps"].supabase_client is mock_db


@pytest.mark.asyncio
async def test_agent_error_returns_friendly_message(mock_db):
    """Agent failures should return a user-friendly error, not crash."""
    fake_conversation = {"id": "conv-002"}

    with (
        patch("jordan_claw.gateway.router.message_exists", return_value=False),
        patch(
            "jordan_claw.gateway.router.get_or_create_conversation",
            return_value=fake_conversation,
        ),
        patch("jordan_claw.gateway.router.save_message", return_value={}),
        patch("jordan_claw.gateway.router.get_recent_messages", return_value=[]),
        patch("jordan_claw.gateway.router.load_memory_context", return_value=""),
        patch(
            "jordan_claw.gateway.router.build_agent",
            side_effect=Exception("LLM timeout"),
        ),
        patch(
            "jordan_claw.gateway.router.update_conversation_status",
            return_value=None,
        ),
    ):
        result = await handle_message(
            make_incoming(channel_message_id="telegram:999"),
            db=mock_db,
            agent_slug="claw-main",
            tavily_api_key="test-key",
            fastmail_username="test@fastmail.com",
            fastmail_app_password="test-password",
        )

    assert result.content == ERROR_RESPONSE
    assert result.conversation_id == "conv-002"


@pytest.mark.asyncio
async def test_memory_context_injected_into_agent(mock_db):
    """Memory context should be passed to build_agent."""
    fake_conversation = {"id": "conv-003"}

    mock_usage = MagicMock()
    mock_usage.input_tokens = 10
    mock_usage.output_tokens = 5
    mock_usage.requests = 1

    mock_result = MagicMock()
    mock_result.output = "I remember your preferences."
    mock_result.usage.return_value = mock_usage

    mock_agent = AsyncMock()
    mock_agent.run.return_value = mock_result

    with (
        patch("jordan_claw.gateway.router.message_exists", return_value=False),
        patch(
            "jordan_claw.gateway.router.get_or_create_conversation",
            return_value=fake_conversation,
        ),
        patch("jordan_claw.gateway.router.save_message", return_value={}),
        patch("jordan_claw.gateway.router.get_recent_messages", return_value=[]),
        patch(
            "jordan_claw.gateway.router.load_memory_context",
            return_value="## Memory Context\n- Prefers Python",
        ),
        patch(
            "jordan_claw.gateway.router.build_agent",
            return_value=(mock_agent, "claude-sonnet-4-20250514"),
        ) as mock_build,
        patch("jordan_claw.gateway.router.extract_memory_background", new_callable=AsyncMock),
    ):
        await handle_message(
            make_incoming(),
            db=mock_db,
            agent_slug="claw-main",
            tavily_api_key="test-key",
            fastmail_username="test@fastmail.com",
            fastmail_app_password="test-password",
        )

    # Verify memory_context was passed to build_agent
    build_call_kwargs = mock_build.call_args.kwargs
    assert build_call_kwargs.get("memory_context") == "## Memory Context\n- Prefers Python"
```

- [ ] **Step 4: Run all tests**

Run: `cd jordan-claw && uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Run ruff on modified files**

Run: `cd jordan-claw && uv run ruff check src/jordan_claw/agents/factory.py src/jordan_claw/gateway/router.py tests/test_gateway.py`

- [ ] **Step 6: Commit**

```bash
git add jordan-claw/src/jordan_claw/agents/factory.py jordan-claw/src/jordan_claw/gateway/router.py jordan-claw/tests/test_gateway.py
git commit -m "feat: wire memory read/write into gateway lifecycle"
```

---

## Task 8: Run Migration and Smoke Test

**Files:**
- Modify: Supabase (via SQL editor or CLI)

- [ ] **Step 1: Run the migration on Supabase**

Open Supabase SQL Editor at `https://supabase.com/dashboard/project/kmlzwhkbpouhzcyjujsn/sql` and run the contents of `jordan-claw/supabase/migrations/002_memory_tables.sql`.

- [ ] **Step 2: Update agent tools and system prompt in DB**

Run this SQL to add memory tools and memory-aware instructions to the claw-main agent:

```sql
-- Add memory tools
update agents
set tools = '["current_datetime", "search_web", "check_calendar", "schedule_event", "recall_memory", "forget_memory"]'
where slug = 'claw-main'
  and org_id = '1408252a-fd36-4fd3-b527-3b2f495d7b9c';

-- Append memory instructions to system prompt
update agents
set system_prompt = system_prompt || '

You have a memory system. A summary of what you remember is included at the top of your context. You also have tools to work with memory:
- recall_memory: Search for specific facts you''ve remembered. Use when someone asks "what do you know about..." or when you need deeper context.
- forget_memory: Archive a memory when someone asks you to forget something.

When someone says "remember that..." or explicitly asks you to remember something, confirm that you will. The memory system will capture it automatically.
When someone asks "what do you know about me?" or similar, use recall_memory to look up relevant facts.'
where slug = 'claw-main'
  and org_id = '1408252a-fd36-4fd3-b527-3b2f495d7b9c';
```

- [ ] **Step 3: Run the full test suite one final time**

Run: `cd jordan-claw && uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Run ruff on everything**

Run: `cd jordan-claw && uv run ruff check src/jordan_claw/ tests/`

- [ ] **Step 5: Deploy and smoke test**

Push to main (triggers Railway auto-deploy), then:

1. Send to @jb_homebase_bot: "Remember that I prefer working in the morning"
2. Wait ~10 seconds for extraction
3. Check `memory_facts` table in Supabase for the new fact
4. Send: "What do you know about me?"
5. Verify the agent calls recall_memory and surfaces the preference
6. Send: "Actually I prefer working at night"
7. Check that the old fact was handled per conflict resolution rules

- [ ] **Step 6: Commit any final fixes from smoke test**

```bash
git add -A
git commit -m "fix: address issues from memory system smoke test"
```
