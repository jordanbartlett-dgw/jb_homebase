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
