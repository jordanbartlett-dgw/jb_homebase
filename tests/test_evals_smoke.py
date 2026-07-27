"""Smoke test for the eval harness wiring.

Builds a 2-case in-memory dataset, runs it against TestModel (no API call), and
asserts the dataset/evaluator/report wiring works end-to-end. Does NOT exercise
the production task_fns — those spend money and are exercised by the nightly
Railway run instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pydantic_evals import Case, Dataset

from evals.run_eval import RunSummary, _build_report_dict, _exit_code
from evals.scorers import RequiredFactsScorer
from evals.types import MemoryRecallExpected, MemoryRecallInputs, MemoryState, SyntheticFact


async def _smoke_task(inputs: MemoryRecallInputs) -> str:
    agent = Agent(TestModel(custom_output_text="uv is the answer"))
    result = await agent.run(inputs.question)
    return str(result.output)


async def _flaky_task(inputs: MemoryRecallInputs) -> str:
    """Raises for the case with no seeded facts, to exercise report.failures."""
    if not inputs.memory_state.facts:
        raise RuntimeError("boom")
    agent = Agent(TestModel(custom_output_text="uv is the answer"))
    result = await agent.run(inputs.question)
    return str(result.output)


def _two_cases() -> list[Case]:
    return [
        Case(
            name="hits_required_fact",
            inputs=MemoryRecallInputs(
                memory_state=MemoryState(
                    facts=[SyntheticFact(category="preference", content="Jordan uses uv")]
                ),
                question="What package manager?",
            ),
            expected_output=MemoryRecallExpected(required_facts=["uv"]),
        ),
        Case(
            name="misses_required_fact",
            inputs=MemoryRecallInputs(
                memory_state=MemoryState(),
                question="Anything?",
            ),
            expected_output=MemoryRecallExpected(required_facts=["pip"]),
        ),
    ]


@pytest.mark.asyncio
async def test_harness_runs_end_to_end() -> None:
    ds = Dataset[MemoryRecallInputs, MemoryRecallExpected, dict](
        name="smoke",
        cases=_two_cases(),
        evaluators=[RequiredFactsScorer()],
    )

    report = await ds.evaluate(_smoke_task, max_concurrency=2, progress=False)

    assert len(report.cases) == 2
    by_name = {c.name: c for c in report.cases}

    assert by_name["hits_required_fact"].scores["required_facts"].value == 1.0
    assert by_name["misses_required_fact"].scores["required_facts"].value == 0.0


@pytest.mark.asyncio
async def test_report_dict_counts_failures_and_carries_results() -> None:
    """A task_fn exception must land in report.failures, not vanish from counts.

    pydantic-evals silently drops exceptions from .cases (see
    feedback_pydantic_evals_silent_drops memory) — this asserts our own report
    building surfaces them instead.
    """
    ds = Dataset[MemoryRecallInputs, MemoryRecallExpected, dict](
        name="smoke",
        cases=_two_cases(),
        evaluators=[RequiredFactsScorer()],
    )

    report = await ds.evaluate(_flaky_task, max_concurrency=2, progress=False)

    assert len(report.cases) == 1
    assert len(report.failures) == 1

    report_dict = _build_report_dict(
        dataset="smoke",
        report=report,
        score=1.0,
        per_evaluator={"required_facts": 1.0},
        passed_cases=1,
        duration_ms=10,
        prev_score=None,
        regression=False,
        experiment_name="smoke@local",
    )

    # total_cases must count the failure, not just the surviving cases.
    assert report_dict["total_cases"] == 2
    assert report_dict["experiment_name"] == "smoke@local"

    assert len(report_dict["failures"]) == 1
    failure = report_dict["failures"][0]
    assert failure["name"] == "misses_required_fact"
    assert "boom" in failure["error_message"]
    assert "trace_id" in failure  # may be None without configured logfire

    case_dict = report_dict["cases"][0]
    assert case_dict["name"] == "hits_required_fact"
    assert "trace_id" in case_dict  # may be None without configured logfire
    assert case_dict["inputs"]
    assert case_dict["output"] == "uv is the answer"
    assert case_dict["scores"] == {"required_facts": 1.0}
    assert case_dict["results"]["required_facts"] == {
        "value": 1.0,
        "reason": case_dict["results"]["required_facts"]["reason"],
    }
    assert "reason" in case_dict["results"]["required_facts"]


def test_exit_code_regression_takes_precedence_over_failures() -> None:
    failing_summary = RunSummary(
        dataset="smoke",
        score=1.0,
        total_cases=2,
        passed_cases=1,
        duration_ms=1,
        prev_score=None,
        regression=False,
        per_evaluator={},
        report_path=Path("unused.json"),
        failures=[{"name": "x", "error_message": "boom", "trace_id": None}],
    )
    assert _exit_code([failing_summary]) == 1

    regressed_summary = RunSummary(
        dataset="smoke",
        score=0.0,
        total_cases=2,
        passed_cases=0,
        duration_ms=1,
        prev_score=1.0,
        regression=True,
        per_evaluator={},
        report_path=Path("unused.json"),
        failures=[{"name": "x", "error_message": "boom", "trace_id": None}],
    )
    # Both a failure and a regression are present — regression wins (exit 2).
    assert _exit_code([failing_summary, regressed_summary]) == 2

    clean_summary = RunSummary(
        dataset="smoke",
        score=1.0,
        total_cases=2,
        passed_cases=2,
        duration_ms=1,
        prev_score=None,
        regression=False,
        per_evaluator={},
        report_path=Path("unused.json"),
        failures=[],
    )
    assert _exit_code([clean_summary]) == 0
