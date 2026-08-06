from __future__ import annotations

from jordan_claw.workout.analysis import judge_overload
from jordan_claw.workout.models import WorkoutLog


def _log(date: str, activity: str = "run", details: dict | None = None) -> WorkoutLog:
    return WorkoutLog(
        id=f"log-{date}-{activity}",
        org_id="org-1",
        logged_date=date,
        activity=activity,
        details=details or {},
    )


def test_run_longer_distance_same_pace_is_positive():
    baseline = _log("2026-07-30", details={"distance_mi": 3.0, "duration_min": 30})
    log = _log("2026-08-04", details={"distance_mi": 3.5, "duration_min": 35})
    result = judge_overload(log, [baseline, log])
    assert result is not None
    assert result.verdict == "positive"
    assert "+0.5 mi" in result.reason
    assert "vs Jul 30" in result.reason


def test_run_shorter_and_slower_is_negative():
    baseline = _log("2026-07-30", details={"distance_mi": 4.0, "duration_min": 36})
    log = _log("2026-08-04", details={"distance_mi": 3.0, "duration_min": 33})
    result = judge_overload(log, [baseline])
    assert result.verdict == "negative"


def test_run_mixed_signals_is_none():
    # More distance but proportionally slower pace: one better, one worse.
    baseline = _log("2026-07-30", details={"distance_mi": 3.0, "duration_min": 30})
    log = _log("2026-08-04", details={"distance_mi": 4.0, "duration_min": 48})
    result = judge_overload(log, [baseline])
    assert result.verdict == "none"


def test_run_within_tolerance_is_none():
    baseline = _log("2026-07-30", details={"distance_mi": 3.0, "duration_min": 30.0})
    log = _log("2026-08-04", details={"distance_mi": 3.02, "duration_min": 30.1})
    result = judge_overload(log, [baseline])
    assert result.verdict == "none"


def test_run_duration_only_longer_is_positive():
    baseline = _log("2026-07-30", details={"duration_min": 20})
    log = _log("2026-08-04", details={"duration_min": 25})
    result = judge_overload(log, [baseline])
    assert result.verdict == "positive"


def test_run_no_earlier_run_is_no_baseline():
    log = _log("2026-08-04", details={"distance_mi": 3.0})
    strength = _log("2026-08-02", activity="strength")
    result = judge_overload(log, [strength, log])
    assert result.verdict == "no_baseline"


def test_run_baseline_outside_lookback_is_no_baseline():
    stale = _log("2026-06-01", details={"distance_mi": 3.0, "duration_min": 30})
    log = _log("2026-08-04", details={"distance_mi": 3.5, "duration_min": 33})
    result = judge_overload(log, [stale])
    assert result.verdict == "no_baseline"


def test_run_unparseable_details_is_no_baseline():
    baseline = _log("2026-07-30", details={"distance_mi": "around 5k"})
    log = _log("2026-08-04", details={"felt": "great"})
    result = judge_overload(log, [baseline])
    assert result.verdict == "no_baseline"


def test_unscored_activities_return_none():
    log = _log("2026-08-04", activity="mobility")
    assert judge_overload(log, []) is None
    assert judge_overload(_log("2026-08-04", activity="rest"), []) is None
    assert judge_overload(_log("2026-08-04", activity="other"), []) is None


def test_run_malformed_logged_date_is_no_baseline():
    log = WorkoutLog(
        id="log-bad",
        org_id="org-1",
        logged_date="not-a-date",
        activity="run",
        details={"distance_mi": 3.0},
    )
    result = judge_overload(log, [])
    assert result is not None
    assert result.verdict == "no_baseline"
    assert "unreadable" in result.reason


def test_run_baseline_with_malformed_date_is_skipped():
    good_baseline = _log("2026-07-30", details={"distance_mi": 3.0, "duration_min": 30})
    bad_baseline = WorkoutLog(
        id="log-bad",
        org_id="org-1",
        logged_date="not-a-date",
        activity="run",
        details={"distance_mi": 2.0, "duration_min": 25},
    )
    log = _log("2026-08-04", details={"distance_mi": 3.5, "duration_min": 35})
    result = judge_overload(log, [bad_baseline, good_baseline])
    assert result is not None
    assert result.verdict == "positive"
    assert "vs Jul 30" in result.reason
