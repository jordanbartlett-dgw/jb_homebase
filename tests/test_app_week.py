from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

from jordan_claw.gateway.app_week import load_workout_week
from jordan_claw.workout.models import WorkoutLog, WorkoutPlan

CHICAGO = ZoneInfo("America/Chicago")
# Thursday Aug 6 2026. Week runs Mon Aug 3 - Sun Aug 9.
NOW = datetime(2026, 8, 6, 9, 0, tzinfo=CHICAGO)

PLAN = WorkoutPlan(
    id="plan-1",
    org_id="org-1",
    status="active",
    starts_on="2026-08-03",
    weeks=[
        {
            "week_number": 1,
            "focus": "base",
            "days": [
                {"day": "Monday", "session_type": "run", "description": "easy run"},
                {"day": "Thursday", "session_type": "strength", "description": "lift"},
                {"day": "Saturday", "session_type": "run", "description": "long run"},
                {"day": "Sunday", "session_type": "rest", "description": "rest"},
            ],
        }
    ],
)

LOGS = [
    WorkoutLog(
        id="log-old",
        org_id="org-1",
        logged_date="2026-07-27",
        activity="run",
        details={"distance_mi": 3.0, "duration_min": 30},
    ),
    WorkoutLog(
        id="log-mon",
        org_id="org-1",
        logged_date="2026-08-03",
        activity="run",
        details={"distance_mi": 3.5, "duration_min": 35},
    ),
]


def _patched(plan, logs):
    return (
        patch(
            "jordan_claw.gateway.app_week.get_active_plan",
            new=AsyncMock(return_value=plan),
        ),
        patch(
            "jordan_claw.gateway.app_week.get_logs_since",
            new=AsyncMock(return_value=logs),
        ),
    )


async def test_week_shape_and_statuses():
    plan_patch, logs_patch = _patched(PLAN, LOGS)
    with plan_patch, logs_patch as logs_query:
        response = await load_workout_week(MagicMock(), org_id="org-1", now=NOW)

    assert response.week_start == "2026-08-03"
    assert response.week_end == "2026-08-09"
    assert response.timezone == "America/Chicago"
    assert response.plan_status == "active"
    assert len(response.days) == 7
    assert [d.date for d in response.days] == [f"2026-08-0{n}" for n in range(3, 10)]

    monday, tuesday, wednesday, thursday, friday, saturday, sunday = response.days
    assert monday.day_status == "logged"
    assert monday.planned.description == "easy run"
    assert tuesday.day_status == "empty"
    assert wednesday.day_status == "empty"
    assert thursday.is_today and thursday.day_status == "today"
    assert saturday.day_status == "upcoming"
    assert sunday.day_status == "rest"
    # Baseline window: 45 days before week_start.
    assert logs_query.await_args.args[2] == "2026-06-19"


async def test_logged_day_carries_verdict_and_reason():
    plan_patch, logs_patch = _patched(PLAN, LOGS)
    with plan_patch, logs_patch:
        response = await load_workout_week(MagicMock(), org_id="org-1", now=NOW)

    log_entry = response.days[0].logs[0]
    assert log_entry.id == "log-mon"
    assert log_entry.verdict == "positive"
    assert "vs Jul 27" in log_entry.reason
    # The 45-day-window log from Jul 27 is a baseline, not a week row.
    all_ids = [entry.id for day in response.days for entry in day.logs]
    assert "log-old" not in all_ids


async def test_no_active_plan_still_shows_logs():
    plan_patch, logs_patch = _patched(None, LOGS)
    with plan_patch, logs_patch:
        response = await load_workout_week(MagicMock(), org_id="org-1", now=NOW)

    assert response.plan_status == "none"
    assert all(day.planned is None for day in response.days)
    assert response.days[0].day_status == "logged"
    assert response.days[0].logs[0].verdict == "positive"


async def test_ended_plan_reports_ended():
    old_plan = PLAN.model_copy(update={"starts_on": "2026-06-01"})
    plan_patch, logs_patch = _patched(old_plan, [])
    with plan_patch, logs_patch:
        response = await load_workout_week(MagicMock(), org_id="org-1", now=NOW)

    assert response.plan_status == "ended"
    assert all(day.planned is None for day in response.days)


async def test_unscored_activity_has_null_verdict():
    mobility = WorkoutLog(
        id="log-mob",
        org_id="org-1",
        logged_date="2026-08-04",
        activity="mobility",
        details={},
    )
    plan_patch, logs_patch = _patched(PLAN, [mobility])
    with plan_patch, logs_patch:
        response = await load_workout_week(MagicMock(), org_id="org-1", now=NOW)

    entry = response.days[1].logs[0]
    assert entry.verdict is None
    assert entry.reason is None
