from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from jordan_claw.tools.calendar import CENTRAL_TZ
from jordan_claw.tools.workout import (
    get_recent_workouts,
    get_workout_plan,
    get_workout_profile_tool,
    log_workout,
    save_workout_plan_tool,
    save_workout_profile,
)
from jordan_claw.workout.models import (
    PlanDay,
    PlanWeek,
    WorkoutLog,
    WorkoutPlan,
    WorkoutProfile,
)


def _make_ctx(org_id: str = "org-001"):
    ctx = MagicMock()
    ctx.deps.org_id = org_id
    ctx.deps.supabase_client = MagicMock()
    return ctx


def _plan() -> WorkoutPlan:
    return WorkoutPlan(
        id="p1", org_id="org-001", status="active", starts_on="2026-07-07",
        rationale="Base building",
        weeks=[PlanWeek(week_number=1, focus="easy volume", days=[
            PlanDay(day="monday", session_type="run", description="Easy 4mi",
                    targets={"distance_mi": 4}),
        ])],
    )


@pytest.mark.asyncio
async def test_get_profile_reports_missing_fields():
    ctx = _make_ctx()
    with patch("jordan_claw.tools.workout.get_workout_profile", return_value=None):
        result = await get_workout_profile_tool(ctx)
    assert "no profile" in result.lower()
    assert "goals" in result


@pytest.mark.asyncio
async def test_get_profile_renders_complete_profile():
    profile = WorkoutProfile(
        org_id="org-001",
        goals={"race": "half marathon"},
        experience="intermediate",
        training_days={"days": ["mon", "wed"]},
    )
    ctx = _make_ctx()
    with patch("jordan_claw.tools.workout.get_workout_profile", return_value=profile):
        result = await get_workout_profile_tool(ctx)
    assert "half marathon" in result
    assert "complete" in result.lower()


@pytest.mark.asyncio
async def test_save_profile_passes_fields():
    ctx = _make_ctx()
    with patch("jordan_claw.tools.workout.upsert_workout_profile") as mock_upsert:
        result = await save_workout_profile(ctx, experience="beginner")
    mock_upsert.assert_called_once_with(
        ctx.deps.supabase_client, "org-001", goals=None, experience="beginner",
        training_days=None, equipment=None, injuries=None, nutrition=None,
        baseline=None,
    )
    assert "saved" in result.lower()


@pytest.mark.asyncio
async def test_get_plan_when_none():
    ctx = _make_ctx()
    with patch("jordan_claw.tools.workout.get_active_plan", return_value=None):
        result = await get_workout_plan(ctx)
    assert "no active plan" in result.lower()


@pytest.mark.asyncio
async def test_save_plan_returns_confirmation():
    ctx = _make_ctx()
    with patch(
        "jordan_claw.tools.workout.save_workout_plan", return_value={"id": "p2"}
    ) as mock_save:
        result = await save_workout_plan_tool(
            ctx, starts_on="2026-07-07", weeks=_plan().weeks, rationale="Base",
        )
    assert mock_save.call_args.kwargs["starts_on"] == "2026-07-07"
    assert "saved" in result.lower()


@pytest.mark.asyncio
async def test_log_workout_defaults_to_today():
    ctx = _make_ctx()
    with patch(
        "jordan_claw.tools.workout.insert_workout_log", return_value={"id": "l1"}
    ) as mock_insert:
        result = await log_workout(ctx, activity="run", notes="legs heavy")
    assert (
        mock_insert.call_args.kwargs["logged_date"]
        == datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")
    )
    assert "logged" in result.lower()


@pytest.mark.asyncio
async def test_get_recent_workouts_formats_logs():
    logs = [WorkoutLog(id="l1", org_id="org-001", logged_date="2026-07-02",
                       activity="run", notes="felt good")]
    ctx = _make_ctx()
    with patch("jordan_claw.tools.workout.get_recent_workout_logs", return_value=logs):
        result = await get_recent_workouts(ctx)
    assert "2026-07-02" in result
    assert "felt good" in result


def test_tools_registered_in_workout_capability():
    from jordan_claw.agents.capabilities import CAPABILITY_REGISTRY

    workout_tools = CAPABILITY_REGISTRY["workout"].toolset.tools
    for name in (
        "get_workout_profile", "save_workout_profile", "get_workout_plan",
        "save_workout_plan", "log_workout", "get_recent_workouts",
    ):
        assert name in workout_tools
