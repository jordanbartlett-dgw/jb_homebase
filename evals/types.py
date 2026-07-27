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


class MedCheckInputs(BaseModel):
    user_message: str
    fixture: str  # key into evals.fixtures.med_check.FIXTURES


class MedCheckExpected(BaseModel):
    required_phrases: list[str] = Field(default_factory=list)
    forbidden_phrases: list[str] = Field(default_factory=list)
    forbidden_in_note: list[str] = Field(
        default_factory=list,
        description=(
            "Phrases checked case-insensitively ONLY against the text after the "
            '"===NOTE===" marker (see evals/tasks/med_check.py::_compose_reply). '
            "If declared and the output has no note marker, scores 0.0 — a "
            "timeline case that produced no note is a failure."
        ),
    )


class EmailTriageInputs(BaseModel):
    """Payload keys mirror events/agentmail.py::_to_payload — from_ maps to
    the {from} template placeholder (from is a Python keyword)."""

    from_: str
    subject: str
    snippet: str


class EmailTriageExpected(BaseModel):
    required_phrases: list[str] = Field(default_factory=list)
    forbidden_phrases: list[str] = Field(default_factory=list)
