from __future__ import annotations

import pytest

from evals.scorers.memory_recall import score_required_facts


@pytest.mark.parametrize(
    ("output", "required"),
    [
        ("He means the Jordan Claw agent platform.", ["Jordan Claw"]),
        ("I’m sorry, but I don’t have that information.", ["don't"]),
        ("Use  uv\nto add it.", ["use uv to"]),
    ],
)
def test_typography_does_not_cause_a_miss(output: str, required: list[str]) -> None:
    assert score_required_facts(output, required) == 1.0


def test_any_alternative_satisfies_a_fact() -> None:
    required = [["don't", "not aware"]]
    assert score_required_facts("I'm not aware of that.", required) == 1.0
    assert score_required_facts("It is HubSpot.", required) == 0.0


def test_alternatives_count_as_one_fact() -> None:
    required = ["uv", ["ask", "would you like"]]
    assert score_required_facts("Would you like me to use uv?", required) == 1.0
    assert score_required_facts("I will use uv.", required) == 0.5


def test_no_required_facts_scores_full() -> None:
    assert score_required_facts("anything", []) == 1.0
