"""Smoke test for the eval harness wiring.

Builds a 2-case in-memory dataset, runs it against TestModel (no API call), and
asserts the dataset/evaluator/report wiring works end-to-end. Does NOT exercise
the production task_fns — those spend money and are exercised by the nightly
Railway run instead.
"""

from __future__ import annotations

import glob
from pathlib import Path

import pytest
import yaml
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pydantic_evals import Case, Dataset

from evals.run_eval import RunSummary, _build_report_dict, _case_accounting, _exit_code
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
        total_cases=2,
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


@pytest.mark.asyncio
async def test_repeat_scoring_matches_single_run_and_counts_cases_not_runs() -> None:
    """repeat=2 against a deterministic task must:

    - produce the same per-evaluator averages as repeat=1 (report.averages()
      group-averages per source case, then averages the groups — for a
      deterministic task every run in a group scores identically, so the
      group average equals the single-run score and the cross-group average
      is unchanged).
    - report passed/total against CASES (2), not RUNS (4) — _case_accounting
      must read report.case_groups() rather than counting report.cases.
    """
    ds = Dataset[MemoryRecallInputs, MemoryRecallExpected, dict](
        name="smoke",
        cases=_two_cases(),
        evaluators=[RequiredFactsScorer()],
    )

    report_once = await ds.evaluate(_smoke_task, max_concurrency=2, progress=False)
    report_repeated = await ds.evaluate(_smoke_task, max_concurrency=2, progress=False, repeat=2)

    # repeat=2 sets source_case_name on every run — case_groups() must fire.
    assert report_once.case_groups() is None
    assert report_repeated.case_groups() is not None
    assert len(report_repeated.cases) == 4  # 2 cases x 2 runs — the raw run count

    once_avg = report_once.averages()
    repeated_avg = report_repeated.averages()
    assert once_avg is not None
    assert repeated_avg is not None
    assert dict(once_avg.scores) == dict(repeated_avg.scores)

    passed_once, total_once = _case_accounting(report_once)
    passed_repeated, total_repeated = _case_accounting(report_repeated)

    # Both runs cover the same 2 source cases; the repeat run must not
    # inflate total_cases to 4 or passed_cases beyond what the case count allows.
    assert total_once == total_repeated == 2
    # hits_required_fact passes, misses_required_fact fails
    assert passed_once == passed_repeated == 1


def test_llm_judge_configs_have_no_hardcoded_model() -> None:
    """Judge model selection is centralized via set_default_judge_model() in the
    CLI (run_eval.py) — a hand-authored `model:` key on any LLMJudge in the
    dataset YAMLs would silently bypass that centralization for just that
    judge. Walk every dataset YAML looking for LLMJudge evaluator entries and
    assert none carry a `model` key.
    """
    dataset_dir = Path(__file__).parent.parent / "evals" / "datasets"
    yaml_paths = sorted(glob.glob(str(dataset_dir / "*.yaml")))
    assert yaml_paths, "expected at least one dataset YAML"

    offenders: list[str] = []

    def _walk(node: object, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "LLMJudge" and isinstance(value, dict) and "model" in value:
                    offenders.append(f"{path}:LLMJudge")
                _walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for i, item in enumerate(node):
                _walk(item, f"{path}[{i}]")

    for yaml_path in yaml_paths:
        data = yaml.safe_load(Path(yaml_path).read_text())
        _walk(data, Path(yaml_path).name)

    assert offenders == []
