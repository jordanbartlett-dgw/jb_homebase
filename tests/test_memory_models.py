from __future__ import annotations

import pytest
from pydantic import ValidationError

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
    with pytest.raises(ValidationError):
        ExtractedFact(
            content="test",
            category="invalid_category",
            source="conversation",
            confidence=0.5,
        )


def test_extracted_fact_rejects_invalid_source():
    with pytest.raises(ValidationError):
        ExtractedFact(
            content="test",
            category="preference",
            source="invalid_source",
            confidence=0.5,
        )
