"""Unit tests for TriagePhraseScorer — no API calls. Runs the scorer through
the harness (pydantic_evals Dataset.evaluate) against a task_fn that just
echoes the case's snippet back as the output, so the scored text is fully
controlled by the test.
"""

from __future__ import annotations

import pytest
from pydantic_evals import Case, Dataset

from evals.scorers import TriagePhraseScorer
from evals.types import EmailTriageExpected, EmailTriageInputs


async def _echo_task(inputs: EmailTriageInputs) -> str:
    return inputs.snippet


async def _score(output_text: str, expected: EmailTriageExpected | None) -> float:
    ds = Dataset[EmailTriageInputs, EmailTriageExpected, dict](
        name="triage_phrase_unit",
        cases=[
            Case(
                name="case",
                inputs=EmailTriageInputs(from_="x@example.com", subject="s", snippet=output_text),
                expected_output=expected,
            )
        ],
        evaluators=[TriagePhraseScorer()],
    )
    report = await ds.evaluate(_echo_task, max_concurrency=1, progress=False)
    return report.cases[0].scores["triage_phrase"].value


@pytest.mark.asyncio
async def test_required_phrase_hit_scores_full() -> None:
    text = "Invoice #4521 for $3,200.00 is due July 31."
    expected = EmailTriageExpected(required_phrases=["invoice", "$3,200.00"])
    assert await _score(text, expected) == 1.0


@pytest.mark.asyncio
async def test_missing_required_phrase_scores_zero() -> None:
    text = "Invoice due soon."
    expected = EmailTriageExpected(required_phrases=["$3,200.00"])
    assert await _score(text, expected) == 0.0


@pytest.mark.asyncio
async def test_forbidden_phrase_scores_zero_even_with_required_hit() -> None:
    text = "Invoice #4521 is due. NOTHING_TO_SEND"
    expected = EmailTriageExpected(
        required_phrases=["invoice"], forbidden_phrases=["NOTHING_TO_SEND"]
    )
    assert await _score(text, expected) == 0.0


@pytest.mark.asyncio
async def test_clean_pass_no_required_no_forbidden() -> None:
    text = "Anything at all."
    expected = EmailTriageExpected()
    assert await _score(text, expected) == 1.0


@pytest.mark.asyncio
async def test_missing_expected_output_fails_closed() -> None:
    text = "Anything at all."
    assert await _score(text, None) == 0.0


@pytest.mark.asyncio
async def test_forbidden_phrase_case_insensitive() -> None:
    text = "nothing_to_send"
    expected = EmailTriageExpected(forbidden_phrases=["NOTHING_TO_SEND"])
    assert await _score(text, expected) == 0.0
