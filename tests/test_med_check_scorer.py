"""Unit tests for PhraseAssertionScorer — no API calls. Runs the scorer through
the harness (pydantic_evals Dataset.evaluate) against a task_fn that just echoes
the case's user_message back as the output, so the scored text is fully
controlled by the test.
"""

from __future__ import annotations

import pytest
from pydantic_evals import Case, Dataset

from evals.scorers import PhraseAssertionScorer
from evals.tasks.med_check import NOTE_MARKER
from evals.types import MedCheckExpected, MedCheckInputs


async def _echo_task(inputs: MedCheckInputs) -> str:
    return inputs.user_message


async def _score(output_text: str, expected: MedCheckExpected | None) -> float:
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
async def test_global_forbidden_fine_to_take_scores_zero() -> None:
    text = "Ondansetron is fine to take. Confirm with pharmacist and cardiology."
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


@pytest.mark.asyncio
async def test_missing_expected_output_fails_closed() -> None:
    text = "Nothing Rett-specific found in the sources checked."
    assert await _score(text, None) == 0.0


@pytest.mark.asyncio
async def test_forbidden_in_note_hit_scores_zero() -> None:
    text = (
        f"Timeline note created.\n\n{NOTE_MARKER}\n"
        "## Questions for the doctor\nIs this consistent with a known pattern?"
    )
    expected = MedCheckExpected(forbidden_in_note=["consistent with"])
    assert await _score(text, expected) == 0.0


@pytest.mark.asyncio
async def test_forbidden_in_note_benign_reply_with_clean_note_passes() -> None:
    """The banned phrase can appear in the chat-facing reply in benign context
    (naming her existing diagnosis, not a new one) as long as it's absent from
    the note body itself — forbidden_in_note only scopes to the note."""
    text = (
        "Noted her congenital Long QT diagnosis is already on file.\n\n"
        f"{NOTE_MARKER}\n## Questions for the doctor\nHas anything changed since May?"
    )
    expected = MedCheckExpected(forbidden_in_note=["diagnosis"])
    assert await _score(text, expected) == 1.0


@pytest.mark.asyncio
async def test_forbidden_in_note_declared_but_no_note_scores_zero() -> None:
    text = "Sure, before I write the note — what range do you want me to use?"
    expected = MedCheckExpected(forbidden_in_note=["diagnosis"])
    assert await _score(text, expected) == 0.0
