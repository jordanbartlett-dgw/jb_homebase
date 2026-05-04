from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SyntheticFact(BaseModel):
    """One row in a synthetic memory_state — mirrors MemoryFact shape minimally."""

    category: Literal["preference", "decision", "entity", "workflow", "relationship"]
    content: str
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)


class SyntheticEvent(BaseModel):
    summary: str
    created_at: str = "2026-05-01T00:00:00Z"


class MemoryState(BaseModel):
    facts: list[SyntheticFact] = Field(default_factory=list)
    events: list[SyntheticEvent] = Field(default_factory=list)


class MemoryRecallInputs(BaseModel):
    memory_state: MemoryState
    question: str


class MemoryRecallExpected(BaseModel):
    required_facts: list[str] = Field(
        description="Substrings that MUST appear in the agent response (case-insensitive)."
    )


class ObsidianRetrievalInputs(BaseModel):
    query: str


class ObsidianRetrievalExpected(BaseModel):
    expected_slugs: list[str] = Field(
        description="Note slugs that should appear in the top-k retrieval results."
    )


class RetrievalOutput(BaseModel):
    """Output of the obsidian_retrieval task fn — returned slugs in rank order."""

    returned_slugs: list[str]
