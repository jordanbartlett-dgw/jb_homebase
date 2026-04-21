from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jordan_claw.memory.models import MemoryFact
from jordan_claw.tools.memory import forget_memory, recall_memory


def _make_ctx(org_id: str = "org-001", db: MagicMock | None = None):
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
        patch(
            "jordan_claw.tools.memory.archive_fact",
            new_callable=AsyncMock,
        ) as mock_archive,
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
    assert "Prefers Python" in result
    assert "Python is great" in result


@pytest.mark.asyncio
async def test_forget_memory_no_matches():
    ctx = _make_ctx()
    with patch("jordan_claw.tools.memory.search_facts", return_value=[]):
        result = await forget_memory(ctx, query="nonexistent")
    assert "no matching" in result.lower() or "nothing" in result.lower()
