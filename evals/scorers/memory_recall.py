from __future__ import annotations

from dataclasses import dataclass

from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from evals.types import MemoryRecallInputs

_QUOTES = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'})


def _normalize(text: str) -> str:
    """Fold case, curly quotes and any run of Unicode whitespace.

    Models emit narrow no-break spaces and curly apostrophes, which made
    correct answers miss a plain substring check.
    """
    return " ".join(text.translate(_QUOTES).split()).casefold()


def score_required_facts(output: str, required: list[str | list[str]]) -> float:
    """Fraction of required facts found in the output.

    A fact given as a list is satisfied by any one of its alternatives.
    """
    if not required:
        return 1.0
    haystack = _normalize(output)
    matched = sum(
        any(_normalize(alt) in haystack for alt in ([fact] if isinstance(fact, str) else fact))
        for fact in required
    )
    return matched / len(required)


@dataclass
class RequiredFactsScorer(Evaluator[MemoryRecallInputs, str, dict]):
    """Score = (matched required facts) / (total required facts).

    Substring match after normalizing case, quotes and whitespace. Fails closed
    (score 0) if expected_output is missing.
    """

    def get_default_evaluation_name(self) -> str:
        return "required_facts"

    def evaluate(
        self,
        ctx: EvaluatorContext[MemoryRecallInputs, str, dict],
    ) -> float:
        if ctx.expected_output is None or not isinstance(ctx.output, str):
            return 0.0
        return score_required_facts(ctx.output, ctx.expected_output.required_facts)
