from __future__ import annotations

from dataclasses import dataclass

from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from evals.types import ObsidianRetrievalInputs, RetrievalOutput


@dataclass
class TopKMembershipScorer(
    Evaluator[ObsidianRetrievalInputs, RetrievalOutput, dict]
):
    """Score = |expected ∩ top_k(returned)| / |expected|.

    Default k=3. Slug match is exact, case-insensitive.
    """

    k: int = 3
    evaluation_name: str = "top_k_membership"

    def evaluate(
        self,
        ctx: EvaluatorContext[ObsidianRetrievalInputs, RetrievalOutput, dict],
    ) -> float:
        if ctx.expected_output is None or not isinstance(ctx.output, RetrievalOutput):
            return 0.0
        expected = {s.lower() for s in ctx.expected_output.expected_slugs}
        if not expected:
            return 1.0
        top = {s.lower() for s in ctx.output.returned_slugs[: self.k]}
        return len(expected & top) / len(expected)
