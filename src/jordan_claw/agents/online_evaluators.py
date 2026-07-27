"""Online evaluators for the `online_eval` capability.

Deterministic checks that run on every sampled agent reply, plus an LLM-judge
rubric for groundedness. See `agents/capabilities.py` for how these wire into
`OnlineEvaluation`.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_evals.evaluators import Evaluator, EvaluatorContext, LLMJudge

_MAX_OUTPUT_CHARS = 20_000


@dataclass
class OutputSanity(Evaluator):
    """Deterministic floor: the reply is a non-empty string under 20k chars."""

    def evaluate(self, ctx: EvaluatorContext) -> bool:
        output = ctx.output
        return isinstance(output, str) and 0 < len(output) < _MAX_OUTPUT_CHARS


GROUNDEDNESS_JUDGE = LLMJudge(
    rubric=(
        "The reply is responsive to the user's request, does not claim to have "
        "taken actions it did not take, and does not contradict information it "
        "retrieved. Judge only what is in the reply."
    ),
    include_input=True,
    model=None,
    assertion=False,
    score={"evaluation_name": "groundedness", "include_reason": True},
)
"""LLM-judge evaluator. `model=None` defers to `set_default_judge_model` (wired
in `main.configure_eval_defaults`). Sample rate is left unset on the
`OnlineEvaluator` wrapper so it inherits the process-wide default (0.0 until
explicitly enabled)."""
