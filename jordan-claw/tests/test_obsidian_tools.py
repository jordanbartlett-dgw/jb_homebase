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
