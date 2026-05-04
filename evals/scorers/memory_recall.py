from __future__ import annotations

from dataclasses import dataclass

from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from evals.types import MemoryRecallInputs


@dataclass
class RequiredFactsScorer(Evaluator[MemoryRecallInputs, str, dict]):
    """Score = (matched required-fact substrings) / (total required-fact substrings).

    Case-insensitive substring match. Fails closed (score 0) if expected_output is missing.
    """

    evaluation_name: str = "required_facts"

    def evaluate(
        self,
        ctx: EvaluatorContext[MemoryRecallInputs, str, dict],
    ) -> float:
        if ctx.expected_output is None or not isinstance(ctx.output, str):
            return 0.0
        required = ctx.expected_output.required_facts
        if not required:
            return 1.0
        haystack = ctx.output.lower()
        matched = sum(1 for fact in required if fact.lower() in haystack)
        return matched / len(required)
