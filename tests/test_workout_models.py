from __future__ import annotations

from jordan_claw.workout.models import (
    PlanDay,  # noqa: F401
    PlanWeek,  # noqa: F401
    WorkoutLog,
    WorkoutPlan,
    WorkoutProfile,
)


def test_profile_missing_core_fields_when_empty():
    profile = WorkoutProfile(org_id="org-1")
    assert profile.missing_core_fields() == ["goals", "experience", "training_days"]


def test_profile_complete_when_core_fields_set():
    profile = WorkoutProfile(
        org_id="org-1",
        goals={"race": "half marathon in October"},
        experience="intermediate",
        training_days={"days": ["mon", "wed", "fri", "sat"], "window": "6-7am"},
    )
    assert profile.missing_core_fields() == []


def test_plan_validates_nested_weeks_from_jsonb():
    row = {
        "id": "p1",
        "org_id": "org-1",
        "status": "active",
        "starts_on": "2026-07-07",
        "rationale": "Base building",
        "weeks": [
            {
                "week_number": 1,
                "focus": "easy volume",
                "days": [
                    {
                        "day": "monday",
                        "session_type": "run",
                        "description": "Easy 4mi",
                        "targets": {"distance_mi": 4},
                    }
                ],
            }
        ],
    }
    plan = WorkoutPlan.model_validate(row)
    assert plan.weeks[0].days[0].session_type == "run"
    assert plan.weeks[0].days[0].targets["distance_mi"] == 4


def test_workout_log_defaults():
    log = WorkoutLog(id="l1", org_id="org-1", logged_date="2026-07-03", activity="run")
    assert log.details == {}
    assert log.notes is None
    assert log.plan_id is None
