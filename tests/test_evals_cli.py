"""Tests for `claw-eval list`, `claw-eval compare`, and the `--json` summary helper.

`list` and `compare` must work with no API keys configured (no get_settings() call), so
these tests never touch Settings — they either exercise the pure helpers directly or run
the CliRunner against a real REGISTRY import with report files monkeypatched into a tmp
dir. `--json` is covered via the pure serialization helper, not by spawning the CLI
process, per the task brief.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

import evals.run_eval as run_eval_module
from evals.registry import REGISTRY
from evals.run_eval import (
    RunSummary,
    _dataset_rows,
    _report_delta,
    _summary_json,
    cli,
)

# --- list ---


def test_dataset_rows_includes_all_six_registered_datasets() -> None:
    rows = _dataset_rows()
    names = [row[0] for row in rows]
    assert set(names) == set(REGISTRY)
    assert len(rows) == len(REGISTRY)


def test_dataset_rows_shape_has_six_columns() -> None:
    for row in _dataset_rows():
        # dataset, cases, evaluators, target_model, baseline, ran_at
        assert len(row) == 6


def test_list_command_runs_and_prints_all_dataset_names() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["list"])
    assert result.exit_code == 0
    for name in REGISTRY:
        assert name in result.output


def test_list_command_missing_baseline_shows_em_dash(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(run_eval_module, "BASELINES_DIR", tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["list"])
    assert result.exit_code == 0
    assert "—" in result.output


# --- compare ---


def _report(score: float, per_evaluator: dict[str, float], cost_usd: float | None = None) -> dict:
    return {
        "score": score,
        "per_evaluator": per_evaluator,
        "passed_cases": 10,
        "total_cases": 10,
        "cost_usd": cost_usd,
    }


def test_report_delta_computes_per_evaluator_and_composite_deltas() -> None:
    older = _report(0.90, {"required_facts": 1.0, "llm_judge": 0.80}, cost_usd=0.05)
    newer = _report(0.95, {"required_facts": 1.0, "llm_judge": 0.90}, cost_usd=0.06)

    delta = _report_delta(older, newer)

    by_name = {row["evaluator"]: row for row in delta["per_evaluator"]}
    assert by_name["required_facts"]["delta"] == 0.0
    assert by_name["llm_judge"]["older"] == 0.80
    assert by_name["llm_judge"]["newer"] == 0.90
    assert abs(by_name["llm_judge"]["delta"] - 0.10) < 1e-9

    assert abs(delta["composite_delta"] - 0.05) < 1e-9
    assert delta["cases_older"] == "10/10"
    assert delta["cost_older"] == 0.05
    assert delta["cost_newer"] == 0.06


def test_report_delta_evaluator_only_on_one_side_has_no_delta() -> None:
    older = _report(0.90, {"llm_judge": 0.90})
    newer = _report(0.90, {"llm_judge": 0.90, "new_scorer": 1.0})

    delta = _report_delta(older, newer)

    by_name = {row["evaluator"]: row for row in delta["per_evaluator"]}
    assert by_name["new_scorer"]["older"] is None
    assert by_name["new_scorer"]["delta"] is None


def test_compare_command_errors_cleanly_with_fewer_than_two_reports(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(run_eval_module, "REPORTS_DIR", tmp_path)
    runner = CliRunner()

    result = runner.invoke(cli, ["compare", "memory_recall"])

    assert result.exit_code == 1
    assert "memory_recall" in result.output
    assert "2" in result.output


def test_compare_command_reads_two_most_recent_reports(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(run_eval_module, "REPORTS_DIR", tmp_path)

    (tmp_path / "memory_recall_20260101T000000Z.json").write_text(
        json.dumps(_report(0.80, {"llm_judge": 0.80}))
    )
    (tmp_path / "memory_recall_20260102T000000Z.json").write_text(
        json.dumps(_report(0.90, {"llm_judge": 0.90}))
    )
    # An older, unrelated report for a different dataset must not be picked up.
    (tmp_path / "obsidian_retrieval_20260103T000000Z.json").write_text(
        json.dumps(_report(1.0, {"top_k_membership": 1.0}))
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["compare", "memory_recall"])

    assert result.exit_code == 0
    assert "0.800" in result.output
    assert "0.900" in result.output
    assert "obsidian_retrieval" not in result.output


# --- --json summary helper ---


def _summary(**overrides: object) -> RunSummary:
    base: dict[str, object] = dict(
        dataset="memory_recall",
        score=0.95,
        total_cases=10,
        passed_cases=10,
        duration_ms=100,
        prev_score=0.90,
        regression=False,
        per_evaluator={"required_facts": 1.0, "llm_judge": 0.9},
        report_path=Path("evals/reports/memory_recall_x.json"),
        failures=[],
        cost_usd=0.10,
        experiment_name="memory_recall@abc123",
    )
    base.update(overrides)
    return RunSummary(**base)  # type: ignore[arg-type]


def test_summary_json_is_valid_json_and_carries_extra_fields() -> None:
    payload = _summary_json(_summary())

    # Must round-trip through json.dumps without a default= coercion.
    line = json.dumps(payload)
    reloaded = json.loads(line)

    assert reloaded["dataset"] == "memory_recall"
    assert reloaded["score"] == 0.95
    assert reloaded["cost_usd"] == 0.10
    assert reloaded["failures"] == []
    assert reloaded["experiment_name"] == "memory_recall@abc123"
    assert reloaded["report_path"] == "evals/reports/memory_recall_x.json"


def test_summary_json_defaults_are_present_when_not_set() -> None:
    payload = _summary_json(_summary(cost_usd=None, experiment_name=""))
    assert payload["cost_usd"] is None
    assert payload["experiment_name"] == ""
    json.dumps(payload)  # still valid JSON
