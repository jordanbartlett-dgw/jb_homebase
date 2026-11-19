from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic_evals.evaluators import Evaluator, EvaluatorContext

from evals.types import CodeModeInputs


@dataclass
class MatchesPattern(Evaluator[CodeModeInputs, str, None]):
    """Case-insensitive regex search over the output.

    For answers where built-in `Contains` is too loose: `Contains: "3"` passes
    on the "3" inside "30 minutes".
    """

    pattern: str

    def matches(self, output: object) -> bool:
        return isinstance(output, str) and bool(re.search(self.pattern, output, re.IGNORECASE))

    def evaluate(self, ctx: EvaluatorContext[CodeModeInputs, str, None]) -> bool:
        return self.matches(ctx.output)
