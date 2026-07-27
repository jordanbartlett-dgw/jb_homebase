"""Tests for schema v2 per-evaluator baselines.

Covers the v2 save/load round-trip, v1 backward-compat loading, and the pure
`_detect_regression` helper (composite-drop, single-evaluator-drop,
evaluator-only-on-one-side, and the v1 composite-only path).
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean

import evals.run_eval as run_eval_module
from evals.run_eval import RunSummary, _detect_regression, _load_baseline, _save_baseline


def _summary(**overrides: object) -> RunSummary:
    base: dict[str, object] = dict(
        dataset="memory_recall",
        score=0.95,
        total_cases=10,
        passed_cases=10,
        duration_ms=100,
        prev_score=None,
        regression=False,
        per_evaluator={"required_facts": 1.0, "llm_judge": 0.9},
        report_path=Path("unused.json"),
        failures=[],
    )
    base.update(overrides)
    return RunSummary(**base)  # type: ignore[arg-type]


# --- v2 round-trip ---


def test_save_baseline_writes_schema_v2(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(run_eval_module, "BASELINES_DIR", tmp_path)
    summary = _summary()

    path = _save_baseline("memory_recall", summary, "abc123")
    payload = json.loads(path.read_text())

    assert payload["schema"] == 2
    assert payload["dataset"] == "memory_recall"
    assert payload["composite"] == 0.95
    assert payload["evaluators"] == {"required_facts": 1.0, "llm_judge": 0.9}
    assert payload["cases_total"] == 10
    assert payload["cases_passed"] == 10
    assert payload["git_sha"] == "abc123"
    assert "ran_at" in payload


def test_v2_round_trip_save_then_load(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(run_eval_module, "BASELINES_DIR", tmp_path)
    summary = _summary()

    _save_baseline("memory_recall", summary, "abc123")
    loaded = _load_baseline("memory_recall")

    assert loaded is not None
    assert loaded["composite"] == 0.95
    assert loaded["evaluators"] == {"required_facts": 1.0, "llm_judge": 0.9}


# --- v1 backward compat ---


def test_load_baseline_v1_backward_compat(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(run_eval_module, "BASELINES_DIR", tmp_path)
    v1_payload = {
        "dataset": "memory_recall",
        "score": 0.975,
        "ran_at": "2026-05-04T20:43:48.821595+00:00",
        "git_sha": "158cfd1",
        "cases_total": 20,
        "cases_passed": 20,
    }
    (tmp_path / "memory_recall.json").write_text(json.dumps(v1_payload))

    loaded = _load_baseline("memory_recall")

    assert loaded is not None
    assert loaded["composite"] == 0.975
    assert loaded["evaluators"] is None
    assert loaded["cases_total"] == 20
    assert loaded["cases_passed"] == 20
    assert loaded["git_sha"] == "158cfd1"


def test_load_baseline_missing_returns_none(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(run_eval_module, "BASELINES_DIR", tmp_path)
    assert _load_baseline("does_not_exist") is None


# --- _detect_regression ---


def test_detect_regression_no_baseline_never_flags() -> None:
    regression, reasons = _detect_regression(0.5, {"llm_judge": 0.5}, None)
    assert regression is False
    assert reasons == []


def test_detect_regression_composite_drop_flags() -> None:
    baseline = {"composite": 0.95, "evaluators": {"llm_judge": 0.95}}
    regression, reasons = _detect_regression(0.85, {"llm_judge": 0.85}, baseline)
    assert regression is True
    assert any("composite" in r for r in reasons)


def test_detect_regression_single_evaluator_drop_with_stable_composite() -> None:
    """Composite barely moves, but one evaluator drops >0.05 — must still flag.

    Large cases_total keeps the small-N guard's effective threshold at the
    flat 5pp floor, matching the pre-guard behavior this test was written for.
    """
    baseline = {
        "composite": 0.925,
        "evaluators": {"required_facts": 1.0, "llm_judge": 0.95},
        "cases_total": 100,
    }
    current_evaluators = {"required_facts": 1.0, "llm_judge": 0.85}
    current_composite = mean(current_evaluators.values())
    assert abs(current_composite - baseline["composite"]) < 0.05  # composite alone wouldn't flag

    regression, reasons = _detect_regression(current_composite, current_evaluators, baseline)

    assert regression is True
    assert any("llm_judge" in r for r in reasons)
    assert not any(r.startswith("composite") for r in reasons)


def test_detect_regression_evaluator_only_in_current_is_informational_not_flagged() -> None:
    baseline = {"composite": 0.95, "evaluators": {"llm_judge": 0.95}}
    current_evaluators = {"llm_judge": 0.95, "new_scorer": 0.1}

    regression, reasons = _detect_regression(0.95, current_evaluators, baseline)

    assert regression is False
    assert any("new evaluator: new_scorer" in r for r in reasons)


def test_detect_regression_evaluator_only_in_baseline_is_informational_not_flagged() -> None:
    baseline = {"composite": 0.95, "evaluators": {"llm_judge": 0.95, "old_scorer": 1.0}}
    current_evaluators = {"llm_judge": 0.95}

    regression, reasons = _detect_regression(0.95, current_evaluators, baseline)

    assert regression is False
    assert any("missing evaluator: old_scorer" in r for r in reasons)


def test_detect_regression_v1_baseline_composite_only() -> None:
    """v1 baseline has no per-evaluator data — only the composite can flag."""
    baseline = {"composite": 0.95, "evaluators": None}

    regression, reasons = _detect_regression(0.85, {"llm_judge": 0.85}, baseline)

    assert regression is True
    assert len(reasons) == 1
    assert "composite" in reasons[0]


def test_detect_regression_v1_baseline_no_drop_no_flag() -> None:
    baseline = {"composite": 0.95, "evaluators": None}

    regression, reasons = _detect_regression(0.94, {"llm_judge": 0.94}, baseline)

    assert regression is False
    assert reasons == []


# --- small-N guard (two-flip regression) ---


def test_detect_regression_small_n_one_flip_does_not_flag() -> None:
    """12-case baseline: a one-case-sized drop (0.083) is under the 0.125 guard."""
    baseline = {
        "composite": 0.95,
        "evaluators": {"llm_judge": 1.0, "other_metric": 0.9},
        "cases_total": 12,
    }
    current_evaluators = {"llm_judge": 0.917, "other_metric": 0.9}
    current_composite = 0.93  # composite drop 0.02, well under the 0.05 composite rule

    regression, reasons = _detect_regression(current_composite, current_evaluators, baseline)

    assert regression is False
    assert not any("llm_judge" in r for r in reasons)


def test_detect_regression_small_n_two_flips_flags_with_scaled_threshold() -> None:
    """12-case baseline: a two-case-sized drop (0.167) exceeds the 0.125 guard."""
    baseline = {
        "composite": 0.95,
        "evaluators": {"llm_judge": 1.0, "other_metric": 0.9},
        "cases_total": 12,
    }
    current_evaluators = {"llm_judge": 0.833, "other_metric": 0.9}
    current_composite = 0.93  # composite drop 0.02, well under the 0.05 composite rule

    regression, reasons = _detect_regression(current_composite, current_evaluators, baseline)

    assert regression is True
    matching = [r for r in reasons if r.startswith("llm_judge")]
    assert len(matching) == 1
    assert "0.125" in matching[0]


def test_detect_regression_large_n_falls_back_to_flat_threshold() -> None:
    """100-case baseline: 1.5/100 (0.015) is below the 0.05 floor, so 0.05 applies."""
    baseline = {
        "composite": 0.95,
        "evaluators": {"llm_judge": 0.95},
        "cases_total": 100,
    }
    current_evaluators = {"llm_judge": 0.89}  # drop 0.06 > 0.05
    current_composite = 0.93  # composite drop 0.02, under the 0.05 composite rule

    regression, reasons = _detect_regression(current_composite, current_evaluators, baseline)

    assert regression is True
    matching = [r for r in reasons if r.startswith("llm_judge")]
    assert len(matching) == 1
    assert "0.05" in matching[0]


def test_detect_regression_trajectory_match_is_informational_only() -> None:
    """TrajectoryMatch never flags on its own, but a big drop surfaces as an info reason."""
    baseline = {
        "composite": 0.95,
        "evaluators": {"TrajectoryMatch": 0.9},
        "cases_total": 12,
    }
    current_evaluators = {"TrajectoryMatch": 0.6}  # drop 0.3, well past any guard
    current_composite = 0.93  # composite drop 0.02, under the 0.05 composite rule

    regression, reasons = _detect_regression(current_composite, current_evaluators, baseline)

    assert regression is False
    assert any(r.startswith("info: TrajectoryMatch") for r in reasons)


def test_detect_regression_composite_flags_regardless_of_small_n_guard() -> None:
    """Composite rule stays flat 5pp even when the baseline is small-N."""
    baseline = {
        "composite": 0.95,
        "evaluators": {"llm_judge": 0.95},
        "cases_total": 12,
    }
    current_evaluators = {"llm_judge": 0.95}  # no per-evaluator drop at all
    current_composite = 0.84  # composite drop 0.11 > 0.05

    regression, reasons = _detect_regression(current_composite, current_evaluators, baseline)

    assert regression is True
    assert any(r.startswith("composite") for r in reasons)
