from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from jordan_claw.db.memory import (
    append_events,
    archive_fact,
    get_active_facts,
    get_memory_context,
    get_recent_events,
    mark_context_stale,
    search_facts,
    upsert_facts,
    upsert_memory_context,
)
from jordan_claw.memory.models import ExtractedEvent, ExtractedFact, MemoryFact

ORG_ID = "org-001"


def _mock_db(select_data=None):
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
        MemoryFact(
            id="f1", org_id=ORG_ID, category="preference", content="Prefers Python",
            source="conversation", confidence=0.5, metadata={},
            created_at="2026-04-01T00:00:00Z", updated_at="2026-04-01T00:00:00Z",
        ),
    ]
    await upsert_facts(db, ORG_ID, facts, existing)
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
        MemoryFact(
            id="f1", org_id=ORG_ID, category="preference", content="Prefers Python",
            source="conversation", confidence=0.9, metadata={},
            created_at="2026-04-01T00:00:00Z", updated_at="2026-04-01T00:00:00Z",
        ),
    ]
    await upsert_facts(db, ORG_ID, facts, existing)
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
async def test_append_events_empty():
    db, query = _mock_db()
    await append_events(db, ORG_ID, [])
    query.insert.assert_not_called()


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
    eq_calls = query.eq.call_args_list
    assert len(eq_calls) >= 3  # org_id, is_archived, category


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


@pytest.mark.asyncio
async def test_get_recent_events():
    events_data = [
        {
            "event_type": "decision",
            "summary": "Chose X",
            "created_at": "2026-04-01T00:00:00Z",
            "context": {},
        }
    ]
    db, query = _mock_db(select_data=events_data)
    result = await get_recent_events(db, ORG_ID)
    assert len(result) == 1
    db.table.assert_called_with("memory_events")
