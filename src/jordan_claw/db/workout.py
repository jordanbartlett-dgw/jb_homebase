from __future__ import annotations

from datetime import UTC, datetime

from supabase._async.client import AsyncClient

from jordan_claw.workout.models import PlanWeek, WorkoutLog, WorkoutPlan, WorkoutProfile

PROFILE_FIELDS = (
    "goals", "experience", "training_days", "equipment",
    "injuries", "nutrition", "baseline",
)


async def get_workout_profile(client: AsyncClient, org_id: str) -> WorkoutProfile | None:
    """Load the workout profile for an org, or None if intake never ran."""
    result = (
        await client.table("workout_profiles")
        .select("*")
        .eq("org_id", org_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return WorkoutProfile.model_validate(result.data[0])


async def upsert_workout_profile(client: AsyncClient, org_id: str, **fields) -> None:
    """Partial upsert: only provided, non-None profile fields are written."""
    data = {k: v for k, v in fields.items() if k in PROFILE_FIELDS and v is not None}
    data["org_id"] = org_id
    data["updated_at"] = datetime.now(UTC).isoformat()
    await client.table("workout_profiles").upsert(data, on_conflict="org_id").execute()


async def get_active_plan(client: AsyncClient, org_id: str) -> WorkoutPlan | None:
    result = (
        await client.table("workout_plans")
        .select("*")
        .eq("org_id", org_id)
        .eq("status", "active")
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return WorkoutPlan.model_validate(result.data[0])


async def save_workout_plan(
    client: AsyncClient,
    org_id: str,
    *,
    starts_on: str,
    weeks: list[PlanWeek],
    rationale: str,
) -> dict:
    """Archive any active plan, then insert the new one as active."""
    await (
        client.table("workout_plans")
        .update({"status": "archived"})
        .eq("org_id", org_id)
        .eq("status", "active")
        .execute()
    )
    result = (
        await client.table("workout_plans")
        .insert(
            {
                "org_id": org_id,
                "starts_on": starts_on,
                "weeks": [w.model_dump() for w in weeks],
                "rationale": rationale,
            }
        )
        .execute()
    )
    return result.data[0]


async def insert_workout_log(
    client: AsyncClient,
    org_id: str,
    *,
    logged_date: str,
    activity: str,
    details: dict | None = None,
    notes: str | None = None,
    plan_id: str | None = None,
) -> dict:
    data: dict = {
        "org_id": org_id,
        "logged_date": logged_date,
        "activity": activity,
        "details": details or {},
    }
    if notes is not None:
        data["notes"] = notes
    if plan_id is not None:
        data["plan_id"] = plan_id
    result = await client.table("workout_logs").insert(data).execute()
    return result.data[0]


async def get_recent_workout_logs(
    client: AsyncClient,
    org_id: str,
    limit: int = 7,
) -> list[WorkoutLog]:
    result = (
        await client.table("workout_logs")
        .select("*")
        .eq("org_id", org_id)
        .order("logged_date", desc=True)
        .limit(limit)
        .execute()
    )
    return [WorkoutLog.model_validate(row) for row in result.data]
