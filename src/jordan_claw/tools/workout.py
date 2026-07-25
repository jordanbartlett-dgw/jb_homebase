from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic_ai import RunContext

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.db.workout import (
    get_active_plan,
    get_latest_workout_log,
    get_logs_for_date,
    get_recent_workout_logs,
    get_workout_profile,
    insert_workout_log,
    save_workout_plan,
    update_workout_log,
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


# TODO(phase-2): HealthKit/Strava ingestion would land logs here without Jordan typing them.
async def log_workout(
    ctx: RunContext[AgentDeps],
    activity: Literal["run", "strength", "mobility", "rest", "other"],
    details: dict | None = None,
    notes: str | None = None,
    logged_date: str | None = None,
    allow_duplicate: bool = False,
) -> str:
    """Record a NEW completed workout when Jordan reports one. details holds numbers
    (distance_mi, duration_min, exercises). logged_date defaults to today.
    NOT for adding detail or corrections to a session already logged in this
    conversation — use amend_last_workout for that. If Jordan genuinely did two
    separate sessions of the same activity on one day, pass allow_duplicate=true."""
    date_str = logged_date or datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")

    if not allow_duplicate:
        same_day = await get_logs_for_date(ctx.deps.supabase_client, ctx.deps.org_id, date_str)
        clashes = [log for log in same_day if log.activity == activity]
        if clashes:
            existing = clashes[0]
            detail = ", ".join(f"{k}={v}" for k, v in existing.details.items())
            summary = " — ".join(p for p in (detail, existing.notes) if p)
            return (
                f"Not logged: a {activity} session for {date_str} already exists "
                f"({summary or 'no details'}). If Jordan is adding detail about that same "
                "session, call amend_last_workout instead. Only if this is a genuinely "
                "separate second session, call log_workout again with allow_duplicate=true."
            )

    await insert_workout_log(
        ctx.deps.supabase_client,
        ctx.deps.org_id,
        logged_date=date_str,
        activity=activity,
        details=details,
        notes=notes,
    )
    return f"Logged {activity} for {date_str}."


async def amend_last_workout(
    ctx: RunContext[AgentDeps],
    details: dict | None = None,
    notes: str | None = None,
    activity: Literal["run", "strength", "mobility", "rest", "other"] | None = None,
) -> str:
    """Add detail or corrections to the most recently logged workout, when Jordan
    follows up about a session that is already logged. New details keys merge into
    the existing ones; notes are appended; activity replaces if given.
    NOT for logging a new session — use log_workout for that."""
    latest = await get_latest_workout_log(ctx.deps.supabase_client, ctx.deps.org_id)
    if latest is None:
        return "No workout logged yet. Use log_workout to record one."

    merged_details = {**latest.details, **(details or {})} if details else None
    merged_notes = None
    if notes:
        merged_notes = f"{latest.notes}\n{notes}" if latest.notes else notes

    await update_workout_log(
        ctx.deps.supabase_client,
        ctx.deps.org_id,
        latest.id,
        details=merged_details,
        notes=merged_notes,
        activity=activity,
    )
    return f"Updated the {activity or latest.activity} log for {latest.logged_date}."


async def get_recent_workouts(ctx: RunContext[AgentDeps], limit: int = 7) -> str:
    """Read recently logged workouts. Use before revising a plan so changes
    reflect what actually happened, not what was scheduled."""
    logs = await get_recent_workout_logs(ctx.deps.supabase_client, ctx.deps.org_id, limit=limit)
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
