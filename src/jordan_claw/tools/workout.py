from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic_ai import RunContext

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.db.workout import (
    get_active_plan,
    get_recent_workout_logs,
    get_workout_profile,
    insert_workout_log,
    save_workout_plan,
    upsert_workout_profile,
)
from jordan_claw.tools.calendar import CENTRAL_TZ
from jordan_claw.workout.models import PlanWeek


async def get_workout_profile_tool(ctx: RunContext[AgentDeps]) -> str:
    """Read Jordan's workout profile (goals, experience, schedule, equipment,
    injuries, nutrition preferences, baseline). Call this at the start of every
    conversation. Reports which core fields are still missing."""
    profile = await get_workout_profile(ctx.deps.supabase_client, ctx.deps.org_id)
    if profile is None:
        return (
            "No profile exists yet. Run the evaluation. "
            "Core fields to collect: goals, experience, training_days. "
            "Also collect: baseline, equipment, injuries, nutrition."
        )
    missing = profile.missing_core_fields()
    status = (
        "Profile is complete."
        if not missing
        else f"Profile incomplete. Missing core fields: {', '.join(missing)}."
    )
    return f"{status}\n\n{profile.model_dump_json(exclude={'org_id'}, indent=2)}"


async def save_workout_profile(
    ctx: RunContext[AgentDeps],
    goals: dict | None = None,
    experience: str | None = None,
    training_days: dict | None = None,
    equipment: dict | None = None,
    injuries: str | None = None,
    nutrition: dict | None = None,
    baseline: dict | None = None,
) -> str:
    """Save workout profile fields as Jordan answers evaluation questions.
    Partial saves are fine; only pass the fields you just learned.
    Keep keys consistent: goals (race, strength_targets, weight), training_days
    (days, window), baseline (weekly_mileage, key_lifts), nutrition
    (preferences, restrictions, targets), equipment (access)."""
    await upsert_workout_profile(
        ctx.deps.supabase_client,
        ctx.deps.org_id,
        goals=goals,
        experience=experience,
        training_days=training_days,
        equipment=equipment,
        injuries=injuries,
        nutrition=nutrition,
        baseline=baseline,
    )
    return "Profile saved."


async def get_workout_plan(ctx: RunContext[AgentDeps]) -> str:
    """Read the current active training plan. Use before answering any question
    about what's scheduled, and before revising the plan."""
    plan = await get_active_plan(ctx.deps.supabase_client, ctx.deps.org_id)
    if plan is None:
        return "No active plan. Propose one once the profile is complete."
    return plan.model_dump_json(exclude={"org_id"}, indent=2)


async def save_workout_plan_tool(
    ctx: RunContext[AgentDeps],
    starts_on: str,
    weeks: list[PlanWeek],
    rationale: str,
) -> str:
    """Store a new training plan after Jordan approves it. Archives the previous
    plan. starts_on is YYYY-MM-DD. Only call after explicit approval."""
    row = await save_workout_plan(
        ctx.deps.supabase_client,
        ctx.deps.org_id,
        starts_on=starts_on,
        weeks=weeks,
        rationale=rationale,
    )
    return f"Plan saved (id {row['id']}). It replaces any previous plan."


async def log_workout(
    ctx: RunContext[AgentDeps],
    activity: Literal["run", "strength", "mobility", "rest", "other"],
    details: dict | None = None,
    notes: str | None = None,
    logged_date: str | None = None,
) -> str:
    """Record a completed workout when Jordan reports one. details holds numbers
    (distance_mi, duration_min, exercises). logged_date defaults to today."""
    date_str = logged_date or datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")
    await insert_workout_log(
        ctx.deps.supabase_client,
        ctx.deps.org_id,
        logged_date=date_str,
        activity=activity,
        details=details,
        notes=notes,
    )
    return f"Logged {activity} for {date_str}."


async def get_recent_workouts(ctx: RunContext[AgentDeps], limit: int = 7) -> str:
    """Read recently logged workouts. Use before revising a plan so changes
    reflect what actually happened, not what was scheduled."""
    logs = await get_recent_workout_logs(
        ctx.deps.supabase_client, ctx.deps.org_id, limit=limit
    )
    if not logs:
        return "No workouts logged yet."
    lines = []
    for log in logs:
        detail = ", ".join(f"{k}={v}" for k, v in log.details.items())
        parts = [f"- [{log.logged_date}] {log.activity}"]
        if detail:
            parts.append(f"({detail})")
        if log.notes:
            parts.append(f"— {log.notes}")
        lines.append(" ".join(parts))
    return "\n".join(lines)
