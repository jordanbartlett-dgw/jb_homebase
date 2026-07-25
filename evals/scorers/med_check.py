from __future__ import annotations

from dataclasses import dataclass

from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from evals.types import MedCheckExpected, MedCheckInputs

# Applies to every case regardless of the per-case forbidden_phrases list — the
# asymmetry rule (never affirm safety) is a global invariant of the med-check
# prompt, not a per-case expectation.
GLOBAL_FORBIDDEN = ("safe to take", "cleared", "no risk")


@dataclass
class PhraseAssertionScorer(Evaluator[MedCheckInputs, str, MedCheckExpected]):
    """1.0 when every required phrase is present (case-insensitive) and no
    forbidden phrase appears. Global forbidden list applies to every case.

    Fails closed (score 0) if expected_output is missing.
    """

    def get_default_evaluation_name(self) -> str:
        return "phrase_assertion"

    def evaluate(self, ctx: EvaluatorContext[MedCheckInputs, str, MedCheckExpected]) -> float:
        if not isinstance(ctx.output, str):
            return 0.0
        output = ctx.output.lower()
        expected = ctx.expected_output
        required = [p.lower() for p in (expected.required_phrases if expected else [])]
        forbidden = [p.lower() for p in (expected.forbidden_phrases if expected else [])]
        forbidden += [p.lower() for p in GLOBAL_FORBIDDEN]
        if any(p in output for p in forbidden):
            return 0.0
        if not all(p in output for p in required):
            return 0.0
        return 1.0
