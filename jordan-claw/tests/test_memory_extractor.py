from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jordan_claw.memory.extractor import (
    build_extraction_prompt,
    create_extraction_agent,
    extract_memory_background,
)
from jordan_claw.memory.models import ExtractedFact, ExtractionResult, MemoryFact


def test_create_extraction_agent(monkeypatch):
    # ANTHROPIC_API_KEY must be set; the agent validates at construction time.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    agent = create_extraction_agent()
    # Pydantic AI 1.x uses output_type; result_type was renamed
    assert agent.output_type is ExtractionResult


def test_build_extraction_prompt_basic():
    prompt = build_extraction_prompt(
        user_message="I prefer working in the morning",
        assistant_response="Noted! I'll keep that in mind.",
        existing_facts=[],
    )
    assert "I prefer working in the morning" in prompt
    assert "Noted!" in prompt
    assert "no existing facts" in prompt.lower() or "No existing facts" in prompt


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
    mock_db = MagicMock()
    mock_result = MagicMock()
    mock_result.output = ExtractionResult(
        facts=[],
        events=[],
        has_corrections=False,
    )

    with (
        patch(
            "jordan_claw.memory.extractor.get_active_facts",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch("jordan_claw.memory.extractor.create_extraction_agent") as mock_create,
        patch(
            "jordan_claw.memory.extractor.upsert_facts",
            new_callable=AsyncMock,
        ) as mock_upsert,
        patch(
            "jordan_claw.memory.extractor.append_events",
            new_callable=AsyncMock,
        ) as mock_append,
        patch(
            "jordan_claw.memory.extractor.mark_context_stale",
            new_callable=AsyncMock,
        ) as mock_stale,
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
    mock_db = MagicMock()

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
        patch(
            "jordan_claw.memory.extractor.get_active_facts",
            new_callable=AsyncMock,
            return_value=[existing_fact],
        ),
        patch("jordan_claw.memory.extractor.create_extraction_agent") as mock_create,
        patch(
            "jordan_claw.memory.extractor.archive_fact",
            new_callable=AsyncMock,
        ) as mock_archive,
        patch(
            "jordan_claw.memory.extractor.upsert_facts",
            new_callable=AsyncMock,
        ),
        patch(
            "jordan_claw.memory.extractor.append_events",
            new_callable=AsyncMock,
        ),
        patch(
            "jordan_claw.memory.extractor.mark_context_stale",
            new_callable=AsyncMock,
        ),
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


@pytest.mark.asyncio
async def test_extract_memory_background_logs_errors():
    mock_db = MagicMock()

    with (
        patch(
            "jordan_claw.memory.extractor.get_active_facts",
            new_callable=AsyncMock,
            side_effect=Exception("DB down"),
        ),
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


@pytest.mark.asyncio
async def test_extract_memory_with_correction_sends_proactive_message():
    """When has_corrections=True and a fact is replaced, a proactive message is sent."""
    mock_db = AsyncMock()

    existing_facts = [
        MemoryFact(
            id="fact-1",
            org_id="org-1",
            category="preference",
            content="Jordan prefers tea",
            source="explicit",
            confidence=0.5,
            created_at="2026-04-01T00:00:00",
            updated_at="2026-04-01T00:00:00",
        )
    ]

    extraction = ExtractionResult(
        facts=[
            ExtractedFact(
                content="Jordan prefers coffee",
                category="preference",
                source="explicit",
                confidence=1.0,
                replaces_fact_id="fact-1",
            )
        ],
        events=[],
        has_corrections=True,
    )

    mock_result = MagicMock()
    mock_result.output = extraction

    with (
        patch(
            "jordan_claw.memory.extractor.get_active_facts",
            new=AsyncMock(return_value=existing_facts),
        ),
        patch("jordan_claw.memory.extractor.create_extraction_agent") as mock_create,
        patch("jordan_claw.memory.extractor.archive_fact", new=AsyncMock()),
        patch("jordan_claw.memory.extractor.upsert_facts", new=AsyncMock()),
        patch("jordan_claw.memory.extractor.append_events", new=AsyncMock()),
        patch("jordan_claw.memory.extractor.mark_context_stale", new=AsyncMock()),
        patch(
            "jordan_claw.memory.extractor.notify_memory_correction",
            new=AsyncMock(),
        ) as mock_notify,
    ):
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_result)
        mock_create.return_value = mock_agent

        await extract_memory_background(mock_db, "org-1", "I prefer coffee", "Noted!")

    mock_notify.assert_called_once_with(
        mock_db, "org-1", "Jordan prefers tea", "Jordan prefers coffee", bot=None
    )
