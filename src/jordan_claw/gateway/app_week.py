from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel
from supabase._async.client import AsyncClient

from jordan_claw.db.workout import get_active_plan, get_logs_since
from jordan_claw.tools.calendar import CENTRAL_TZ
from jordan_claw.workout.analysis import (
    BASELINE_LOOKBACK_DAYS,
    DayStatus,
    Verdict,
    day_status,
    judge_overload,
    plan_status_for_week,
    planned_for_date,
)


class PlannedSession(BaseModel):
    session_type: str
    description: str
    targets: dict = {}


class LoggedWorkoutEntry(BaseModel):
    id: str
    activity: str
    details: dict
    notes: str | None = None
    verdict: Verdict | None = None
    reason: str | None = None


class WeekDay(BaseModel):
    date: str
    is_today: bool
    planned: PlannedSession | None
    logs: list[LoggedWorkoutEntry]
    day_status: DayStatus


class WorkoutWeekResponse(BaseModel):
    """The current Mon-Sun training week: plan ahead, logs + verdicts behind."""

    week_start: str
    week_end: str
    timezone: str
    plan_status: Literal["active", "none", "ended"]
    days: list[WeekDay]


async def load_workout_week(
    db: AsyncClient,
    *,
    org_id: str,
    now: datetime | None = None,
) -> WorkoutWeekResponse:
    """Server-truth weekly schedule. One plan read, one log-window read."""
    current = now.astimezone(CENTRAL_TZ) if now is not None else datetime.now(CENTRAL_TZ)
    today = current.date()
    week_start = today - timedelta(days=today.weekday())
    window_start = week_start - timedelta(days=BASELINE_LOOKBACK_DAYS)

    plan = await get_active_plan(db, org_id)
    all_logs = await get_logs_since(db, org_id, window_start.isoformat())

    active_plan = plan if plan_status_for_week(plan, week_start) == "active" else None

    days: list[WeekDay] = []
    for offset in range(7):
        target = week_start + timedelta(days=offset)
        planned = planned_for_date(active_plan, target)
        day_logs = [log for log in all_logs if log.logged_date == target.isoformat()]
        entries = []
        for log in day_logs:
            result = judge_overload(log, all_logs)
            entries.append(
                LoggedWorkoutEntry(
                    id=log.id,
                    activity=log.activity,
                    details=log.details,
                    notes=log.notes,
                    verdict=result.verdict if result else None,
                    reason=result.reason if result else None,
                )
            )
        days.append(
            WeekDay(
                date=target.isoformat(),
                is_today=target == today,
                planned=None
                if planned is None
                else PlannedSession(
                    session_type=planned.session_type,
                    description=planned.description,
                    targets=planned.targets,
                ),
                logs=entries,
                day_status=day_status(target, today, planned, has_logs=bool(entries)),
            )
        )

    return WorkoutWeekResponse(
        week_start=week_start.isoformat(),
        week_end=(week_start + timedelta(days=6)).isoformat(),
        timezone=str(CENTRAL_TZ),
        plan_status=plan_status_for_week(plan, week_start),
        days=days,
    )
