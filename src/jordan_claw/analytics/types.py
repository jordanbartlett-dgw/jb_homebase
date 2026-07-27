from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class RunKind(StrEnum):
    """Mirrors the CHECK constraint on usage_events.run_kind (migrations 006, 013, 033)."""

    USER_MESSAGE = "user_message"
    PROACTIVE = "proactive"
    MEMORY_EXTRACT = "memory_extract"
    EVAL = "eval"
    EVENT = "event"
    VOICE = "voice"
    CLASSIFIER = "classifier"
    TRANSCRIPTION = "transcription"


@dataclass(frozen=True, slots=True)
class AgentRunResult[OutputT]:
    """Result of one instrumented agent run.

    Generic over the agent's output type so structured-output agents
    (e.g. memory extractor returning ExtractionResult) type-check correctly.
    """

    output: OutputT
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: Decimal | None
    duration_ms: int
    tool_call_count: int
    model: str
    success: bool
    error_type: str | None = None
    traceparent: str | None = None
