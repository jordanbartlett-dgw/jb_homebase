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
        {
            "event_type": "decision",
            "summary": "Picked Railway for hosting",
            "created_at": "2026-04-01T10:00:00Z",
        },
    ]
    result = render_context_block(facts=[], events=events)
    assert "### Recent Activity" in result
    assert "Picked Railway for hosting" in result


def test_render_context_block_respects_token_budget():
    facts = [
        _make_fact(id=f"f{i}", content=f"Fact number {i} with some extra text to use tokens")
        for i in range(100)
    ]
    result = render_context_block(facts=facts, events=[], max_tokens=200)
    assert result.count("- ") < 100


def test_render_context_block_prioritizes_high_confidence():
    facts = [
        _make_fact(id="low", content="Low confidence fact", confidence=0.3),
        _make_fact(id="high", content="High confidence fact", confidence=1.0),
    ]
    result = render_context_block(facts=facts, events=[], max_tokens=100)
    assert "High confidence fact" in result


@pytest.mark.asyncio
async def test_load_memory_context_uses_cache():
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
        patch(
            "jordan_claw.memory.reader.upsert_memory_context",
            new_callable=AsyncMock,
        ) as mock_upsert,
    ):
        result = await load_memory_context(mock_db, "org-001")
    assert "Fresh fact" in result
    mock_upsert.assert_called_once()


@pytest.mark.asyncio
async def test_load_memory_context_recomputes_when_no_cache():
    mock_db = MagicMock()
    facts = [_make_fact(content="New fact")]
    with (
        patch("jordan_claw.memory.reader.get_memory_context", return_value=None),
        patch("jordan_claw.memory.reader.get_active_facts", return_value=facts),
        patch("jordan_claw.memory.reader.get_recent_events", return_value=[]),
        patch(
            "jordan_claw.memory.reader.upsert_memory_context",
            new_callable=AsyncMock,
        ),
    ):
        result = await load_memory_context(mock_db, "org-001")
    assert "New fact" in result
