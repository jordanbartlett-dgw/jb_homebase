from __future__ import annotations

from datetime import date

from jordan_claw.workout.analysis import (
    day_status,
    judge_overload,
    plan_status_for_week,
    planned_for_date,
)
from jordan_claw.workout.models import PlanDay, PlanWeek, WorkoutLog, WorkoutPlan


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


def test_strength_heavier_weight_is_positive():
    baseline = _log(
        "2026-07-29",
        activity="strength",
        details={"exercises": [{"name": "squat", "weight": 185, "sets": 3, "reps": 5}]},
    )
    log = _log(
        "2026-08-05",
        activity="strength",
        details={"exercises": [{"name": "squat", "weight": 195, "sets": 3, "reps": 5}]},
    )
    result = judge_overload(log, [baseline])
    assert result.verdict == "positive"
    assert "+10 lb squat" in result.reason
    assert "vs Jul 29" in result.reason


def test_strength_same_weight_more_reps_is_positive():
    baseline = _log(
        "2026-07-29",
        activity="strength",
        details={"exercises": [{"name": "bench", "weight": 135, "sets": 3, "reps": 5}]},
    )
    log = _log(
        "2026-08-05",
        activity="strength",
        details={"exercises": [{"name": "bench", "weight": 135, "sets": 3, "reps": 6}]},
    )
    result = judge_overload(log, [baseline])
    assert result.verdict == "positive"
    assert "+1 rep bench" in result.reason


def test_strength_same_weight_more_sets_is_positive():
    baseline = _log(
        "2026-07-29",
        activity="strength",
        details={"exercises": [{"name": "squat", "weight": 185, "sets": 3, "reps": 5}]},
    )
    log = _log(
        "2026-08-05",
        activity="strength",
        details={"exercises": [{"name": "squat", "weight": 185, "sets": 5, "reps": 5}]},
    )
    result = judge_overload(log, [baseline])
    assert result.verdict == "positive"
    assert "+2 sets squat" in result.reason


def test_strength_same_weight_more_volume_via_sets_is_positive():
    baseline = _log(
        "2026-07-29",
        activity="strength",
        details={"exercises": [{"name": "squat", "weight": 185, "sets": 3, "reps": 5}]},
    )
    log = _log(
        "2026-08-05",
        activity="strength",
        details={"exercises": [{"name": "squat", "weight": 185, "sets": 5, "reps": 4}]},
    )
    result = judge_overload(log, [baseline])
    assert result.verdict == "positive"
    assert "+5 total reps squat" in result.reason


def test_strength_same_weight_fewer_sets_is_negative():
    baseline = _log(
        "2026-07-29",
        activity="strength",
        details={"exercises": [{"name": "squat", "weight": 185, "sets": 5, "reps": 5}]},
    )
    log = _log(
        "2026-08-05",
        activity="strength",
        details={"exercises": [{"name": "squat", "weight": 185, "sets": 3, "reps": 5}]},
    )
    result = judge_overload(log, [baseline])
    assert result.verdict == "negative"


def test_strength_reps_only_more_volume_is_positive():
    """No weight keys on either side (e.g. plank hold): volume up still scores positive."""
    baseline = _log(
        "2026-07-29",
        activity="strength",
        details={"exercises": [{"name": "plank", "reps": 30, "sets": 2}]},
    )
    log = _log(
        "2026-08-05",
        activity="strength",
        details={"exercises": [{"name": "plank", "reps": 40, "sets": 2}]},
    )
    result = judge_overload(log, [baseline])
    assert result.verdict == "positive"


def test_strength_lighter_weight_is_negative():
    baseline = _log(
        "2026-07-29",
        activity="strength",
        details={"exercises": [{"name": "squat", "weight": 195}]},
    )
    log = _log(
        "2026-08-05",
        activity="strength",
        details={"exercises": [{"name": "squat", "weight": 185}]},
    )
    result = judge_overload(log, [baseline])
    assert result.verdict == "negative"


def test_strength_mixed_exercises_is_none():
    baseline = _log(
        "2026-07-29",
        activity="strength",
        details={
            "exercises": [
                {"name": "squat", "weight": 185, "reps": 5},
                {"name": "bench", "weight": 135, "reps": 5},
            ]
        },
    )
    log = _log(
        "2026-08-05",
        activity="strength",
        details={
            "exercises": [
                {"name": "squat", "weight": 195, "reps": 5},
                {"name": "bench", "weight": 135, "reps": 4},
            ]
        },
    )
    result = judge_overload(log, [baseline])
    assert result.verdict == "none"


def test_strength_split_routine_matches_per_exercise_across_sessions():
    """Push day compares against the last push day, skipping leg day between."""
    push_baseline = _log(
        "2026-07-27",
        activity="strength",
        details={"exercises": [{"name": "bench", "weight": 135, "reps": 5}]},
    )
    leg_day = _log(
        "2026-08-03",
        activity="strength",
        details={"exercises": [{"name": "squat", "weight": 185, "reps": 5}]},
    )
    log = _log(
        "2026-08-05",
        activity="strength",
        details={"exercises": [{"name": "bench", "weight": 145, "reps": 5}]},
    )
    result = judge_overload(log, [push_baseline, leg_day, log])
    assert result.verdict == "positive"
    assert "vs Jul 27" in result.reason


def test_strength_exercise_names_normalized():
    baseline = _log(
        "2026-07-29",
        activity="strength",
        details={"exercises": [{"name": "  Bench Press ", "weight": 135}]},
    )
    log = _log(
        "2026-08-05",
        activity="strength",
        details={"exercises": [{"name": "bench press", "weight": 145}]},
    )
    result = judge_overload(log, [baseline])
    assert result.verdict == "positive"


def test_strength_no_matching_exercises_is_no_baseline():
    baseline = _log(
        "2026-07-29",
        activity="strength",
        details={"exercises": [{"name": "deadlift", "weight": 225}]},
    )
    log = _log(
        "2026-08-05",
        activity="strength",
        details={"exercises": [{"name": "overhead press", "weight": 95}]},
    )
    result = judge_overload(log, [baseline])
    assert result.verdict == "no_baseline"


def test_strength_dict_shaped_exercises_parse():
    """The LLM sometimes writes exercises as a name->stats mapping."""
    baseline = _log(
        "2026-07-29",
        activity="strength",
        details={"exercises": {"squat": {"weight": 185, "reps": 5}}},
    )
    log = _log(
        "2026-08-05",
        activity="strength",
        details={"exercises": {"squat": {"weight": 195, "reps": 5}}},
    )
    result = judge_overload(log, [baseline])
    assert result.verdict == "positive"


def test_strength_malformed_exercises_is_no_baseline():
    baseline = _log("2026-07-29", activity="strength", details={"exercises": "heavy day"})
    log = _log("2026-08-05", activity="strength", details={})
    result = judge_overload(log, [baseline])
    assert result.verdict == "no_baseline"


def test_strength_zero_weight_baseline_then_weighted_is_positive():
    """Bodyweight exercise (weight 0) upgraded to weighted (e.g., weighted vest)."""
    baseline = _log(
        "2026-07-29",
        activity="strength",
        details={"exercises": [{"name": "pushup", "weight": 0, "reps": 20}]},
    )
    log = _log(
        "2026-08-05",
        activity="strength",
        details={"exercises": [{"name": "pushup", "weight": 25, "reps": 20}]},
    )
    result = judge_overload(log, [baseline])
    assert result.verdict == "positive"
    assert "+25 lb pushup" in result.reason


def _plan(starts_on: str, n_weeks: int = 2) -> WorkoutPlan:
    return WorkoutPlan(
        id="plan-1",
        org_id="org-1",
        status="active",
        starts_on=starts_on,
        weeks=[
            PlanWeek(
                week_number=i + 1,
                focus=f"week {i + 1}",
                days=[
                    PlanDay(day="Monday", session_type="run", description=f"w{i + 1} easy run"),
                    PlanDay(day="Wednesday", session_type="strength", description="lift"),
                    PlanDay(day="Sunday", session_type="rest", description="rest"),
                ],
            )
            for i in range(n_weeks)
        ],
    )


def test_planned_for_date_maps_week_and_weekday():
    plan = _plan("2026-08-03")  # a Monday
    assert planned_for_date(plan, date(2026, 8, 3)).description == "w1 easy run"
    assert planned_for_date(plan, date(2026, 8, 10)).description == "w2 easy run"
    assert planned_for_date(plan, date(2026, 8, 5)).session_type == "strength"
    assert planned_for_date(plan, date(2026, 8, 4)) is None  # Tuesday: nothing planned


def test_planned_for_date_outside_plan_is_none():
    plan = _plan("2026-08-03", n_weeks=1)
    assert planned_for_date(plan, date(2026, 8, 2)) is None  # before starts_on
    assert planned_for_date(plan, date(2026, 8, 10)) is None  # past last week
    assert planned_for_date(None, date(2026, 8, 3)) is None


def test_plan_status_for_week():
    plan = _plan("2026-08-03", n_weeks=1)  # covers Aug 3-9
    assert plan_status_for_week(plan, date(2026, 8, 3)) == "active"
    assert plan_status_for_week(plan, date(2026, 8, 10)) == "ended"
    assert plan_status_for_week(None, date(2026, 8, 3)) == "none"


def test_day_status_rules():
    today = date(2026, 8, 6)  # Thursday
    run = PlanDay(day="Monday", session_type="run", description="easy run")
    rest = PlanDay(day="Sunday", session_type="rest", description="rest")

    assert day_status(date(2026, 8, 3), today, run, has_logs=True) == "logged"
    assert day_status(date(2026, 8, 3), today, run, has_logs=False) == "missed"
    assert day_status(date(2026, 8, 2), today, rest, has_logs=False) == "rest"
    assert day_status(date(2026, 8, 7), today, run, has_logs=False) == "upcoming"
    assert day_status(today, today, run, has_logs=False) == "today"
    assert day_status(today, today, run, has_logs=True) == "logged"
    assert day_status(today, today, None, has_logs=False) == "empty"
    assert day_status(date(2026, 8, 4), today, None, has_logs=False) == "empty"
    assert day_status(date(2026, 8, 8), today, None, has_logs=False) == "empty"


def test_planned_for_date_malformed_starts_on_returns_none():
    plan = _plan("garbage")  # malformed date
    assert planned_for_date(plan, date(2026, 8, 3)) is None


def test_plan_status_for_week_malformed_starts_on_returns_none():
    plan = _plan("garbage")  # malformed date
    assert plan_status_for_week(plan, date(2026, 8, 3)) == "none"
