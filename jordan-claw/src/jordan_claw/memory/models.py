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
