"""Tests for `claw-eval list`, `claw-eval compare`, and the `--json` summary helper.

`list` and `compare` must work with no API keys configured (no get_settings() call), so
these tests never touch Settings. They either exercise the pure helpers directly or run
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
    REPORTS_KEEP_PER_DATASET,
    RunSummary,
    _dataset_rows,
    _prune_reports,
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


# --- report pruning ---


def _write_reports(reports_dir: Path, dataset: str, count: int) -> list[Path]:
    """Write `count` fake report files with lexicographically-increasing names."""
    paths = []
    for i in range(count):
        ts = f"202601{(i // 24) % 28 + 1:02d}T{i % 24:02d}0000Z"
        path = reports_dir / f"{dataset}_{ts}.json"
        path.write_text("{}")
        paths.append(path)
    return paths


def test_prune_reports_keeps_only_newest_n(tmp_path: Path) -> None:
    paths = _write_reports(tmp_path, "memory_recall", 10)

    _prune_reports(tmp_path, "memory_recall", keep=4)

    remaining = sorted(p.name for p in tmp_path.glob("*.json"))
    expected = sorted(p.name for p in paths)[-4:]
    assert remaining == expected


def test_prune_reports_noop_when_under_limit(tmp_path: Path) -> None:
    _write_reports(tmp_path, "memory_recall", 3)

    _prune_reports(tmp_path, "memory_recall", keep=60)

    assert len(list(tmp_path.glob("*.json"))) == 3


def test_prune_reports_ignores_non_json_files(tmp_path: Path) -> None:
    _write_reports(tmp_path, "memory_recall", 5)
    (tmp_path / "notes.txt").write_text("keep me")

    _prune_reports(tmp_path, "memory_recall", keep=2)

    assert (tmp_path / "notes.txt").exists()
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_prune_reports_is_scoped_per_dataset_not_global_sort(tmp_path: Path) -> None:
    """Reproduces the cross-dataset bug: pruning must never sort all *.json
    together (that sorts purely on the dataset-name prefix, deleting fresh
    reports from an alphabetically-early dataset while keeping ancient ones
    from a later dataset). code_mode < tool_routing lexicographically, so 3
    ancient tool_routing reports plus 3 just-written code_mode reports, with
    keep=3, must retain ALL of the fresh code_mode files and ALL of the
    tool_routing files (each dataset is independently under its own limit).
    """
    ancient = _write_reports(tmp_path, "tool_routing", 3)
    fresh = _write_reports(tmp_path, "code_mode", 3)
    # Make the "ancient" set sort earlier by timestamp than the "fresh" set,
    # while still being an alphabetically-LATER dataset name.
    for i, path in enumerate(ancient):
        path.rename(tmp_path / f"tool_routing_202501{i + 1:02d}T000000Z.json")
    for i, path in enumerate(fresh):
        path.rename(tmp_path / f"code_mode_202607{i + 1:02d}T000000Z.json")

    _prune_reports(tmp_path, "code_mode", keep=3)
    _prune_reports(tmp_path, "tool_routing", keep=3)

    remaining = {p.name for p in tmp_path.glob("*.json")}
    assert remaining == {
        "code_mode_20260701T000000Z.json",
        "code_mode_20260702T000000Z.json",
        "code_mode_20260703T000000Z.json",
        "tool_routing_20250101T000000Z.json",
        "tool_routing_20250102T000000Z.json",
        "tool_routing_20250103T000000Z.json",
    }


def test_prune_reports_only_touches_its_own_dataset(tmp_path: Path) -> None:
    """Pruning dataset A must never delete dataset B's files, even when B is
    over ITS OWN limit. Each call is scoped to one dataset's glob."""
    _write_reports(tmp_path, "memory_recall", 15)
    _write_reports(tmp_path, "obsidian_retrieval", 15)

    _prune_reports(tmp_path, "memory_recall", keep=5)

    assert len(list(tmp_path.glob("memory_recall_*.json"))) == 5
    assert len(list(tmp_path.glob("obsidian_retrieval_*.json"))) == 15


def test_reports_keep_per_dataset_default_is_ten() -> None:
    assert REPORTS_KEEP_PER_DATASET == 10
