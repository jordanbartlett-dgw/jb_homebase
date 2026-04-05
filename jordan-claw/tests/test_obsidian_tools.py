from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai import RunContext

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.tools.obsidian import create_source_note, fetch_article, read_note, search_notes


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


@pytest.mark.asyncio
@patch("jordan_claw.tools.obsidian.AsyncTavilyClient")
async def test_fetch_article_returns_content(mock_tavily_cls):
    mock_client = AsyncMock()
    mock_client.extract.return_value = {
        "results": [
            {"raw_content": "This is the article body text."}
        ]
    }
    mock_tavily_cls.return_value = mock_client
    ctx = _make_ctx()
    result = await fetch_article(ctx, url="https://example.com/article")
    assert "https://example.com/article" in result
    assert "This is the article body text." in result
    mock_tavily_cls.assert_called_once_with(api_key="test")


@pytest.mark.asyncio
@patch("jordan_claw.tools.obsidian.AsyncTavilyClient")
async def test_fetch_article_no_results(mock_tavily_cls):
    mock_client = AsyncMock()
    mock_client.extract.return_value = {"results": []}
    mock_tavily_cls.return_value = mock_client
    ctx = _make_ctx()
    result = await fetch_article(ctx, url="https://example.com/bad")
    assert "Could not extract" in result


@pytest.mark.asyncio
@patch("jordan_claw.tools.obsidian.AsyncTavilyClient")
async def test_fetch_article_truncates_long_content(mock_tavily_cls):
    mock_client = AsyncMock()
    mock_client.extract.return_value = {
        "results": [
            {"raw_content": "A" * 20000}
        ]
    }
    mock_tavily_cls.return_value = mock_client
    ctx = _make_ctx()
    result = await fetch_article(ctx, url="https://example.com/long")
    assert "[Content truncated]" in result
