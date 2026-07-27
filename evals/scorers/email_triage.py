"""TriagePhraseScorer: a leaner binary phrase-presence scorer for the
email_triage dataset. Deliberately not a reuse of med_check's
PhraseAssertionScorer — that scorer carries med_check-specific NOTE_MARKER
splitting and a global forbidden-phrase list that don't apply here. This
scorer is just required_phrases (all must appear, case-insensitive) and
forbidden_phrases (none may appear)."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from evals.types import EmailTriageExpected, EmailTriageInputs


@dataclass
class TriagePhraseScorer(Evaluator[EmailTriageInputs, str, EmailTriageExpected]):
    """1.0 when every required phrase is present (case-insensitive) and no
    forbidden phrase appears in the output. Fails closed (0.0) if
    expected_output is missing."""

    def get_default_evaluation_name(self) -> str:
        return "triage_phrase"

    def evaluate(self, ctx: EvaluatorContext[EmailTriageInputs, str, EmailTriageExpected]) -> float:
        if ctx.expected_output is None or not isinstance(ctx.output, str):
            return 0.0
        output = ctx.output.lower()
        required = [p.lower() for p in ctx.expected_output.required_phrases]
        forbidden = [p.lower() for p in ctx.expected_output.forbidden_phrases]
        if any(p in output for p in forbidden):
            return 0.0
        if not all(p in output for p in required):
            return 0.0
        return 1.0
