"""MatchesPattern: whole-token answer checks for code_mode cases."""

from __future__ import annotations

import pytest

from evals.scorers import MatchesPattern

COUNT_IS_THREE = r"\b(3|three)\b"


def _matches(pattern: str, output: object) -> bool:
    return MatchesPattern(pattern=pattern).matches(output)


@pytest.mark.parametrize(
    "output",
    [
        "You had **3** workouts of 30 minutes or longer.",
        "Three of your last five workouts were 30 minutes or longer.",
    ],
)
def test_accepts_the_count_as_a_digit_or_a_word(output: str) -> None:
    assert _matches(COUNT_IS_THREE, output)


def test_rejects_a_wrong_answer_that_only_mentions_30() -> None:
    """The old `Contains: "3"` passed this on the "3" inside "30"."""
    assert not _matches(COUNT_IS_THREE, "None of your last 5 workouts were 30 minutes or longer.")


def test_rejects_non_string_output() -> None:
    assert not _matches(COUNT_IS_THREE, None)
