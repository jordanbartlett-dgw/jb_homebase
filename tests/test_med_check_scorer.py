"""Unit tests for PhraseAssertionScorer — no API calls. Runs the scorer through
the harness (pydantic_evals Dataset.evaluate) against a task_fn that just echoes
the case's user_message back as the output, so the scored text is fully
controlled by the test.
"""

from __future__ import annotations

import pytest
from pydantic_evals import Case, Dataset

from evals.scorers import PhraseAssertionScorer
from evals.types import MedCheckExpected, MedCheckInputs


async def _echo_task(inputs: MedCheckInputs) -> str:
    return inputs.user_message


async def _score(output_text: str, expected: MedCheckExpected) -> float:
    ds = Dataset[MedCheckInputs, MedCheckExpected, dict](
        name="phrase_assertion_unit",
        cases=[
            Case(
                name="case",
                inputs=MedCheckInputs(user_message=output_text, fixture="unused"),
                expected_output=expected,
            )
        ],
        evaluators=[PhraseAssertionScorer()],
    )
    report = await ds.evaluate(_echo_task, max_concurrency=1, progress=False)
    return report.cases[0].scores["phrase_assertion"].value


@pytest.mark.asyncio
async def test_required_phrase_hit_scores_full() -> None:
    text = "Ondansetron is on CredibleMeds Known Risk. Confirm with pharmacist and cardiology."
    expected = MedCheckExpected(required_phrases=["ondansetron", "pharmacist"])
    assert await _score(text, expected) == 1.0


@pytest.mark.asyncio
async def test_missing_required_phrase_scores_zero() -> None:
    text = "Confirm with pharmacist and cardiology before starting."
    expected = MedCheckExpected(required_phrases=["ondansetron"])
    assert await _score(text, expected) == 0.0


@pytest.mark.asyncio
async def test_global_forbidden_phrase_scores_zero_even_with_required_hit() -> None:
    text = "Ondansetron is safe to take. Confirm with pharmacist and cardiology."
    expected = MedCheckExpected(required_phrases=["ondansetron"])
    assert await _score(text, expected) == 0.0


@pytest.mark.asyncio
async def test_case_forbidden_phrase_scores_zero() -> None:
    text = "Which one did you mean? Flagged - raise this before she takes it."
    expected = MedCheckExpected(
        required_phrases=["which"], forbidden_phrases=["flagged - raise this"]
    )
    assert await _score(text, expected) == 0.0


@pytest.mark.asyncio
async def test_clean_pass_no_required_no_forbidden() -> None:
    text = "Nothing Rett-specific found in the sources checked."
    expected = MedCheckExpected()
    assert await _score(text, expected) == 1.0
