from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class WorkoutProfile(BaseModel):
    """One row from workout_profiles. All content fields nullable; intake fills them."""

    model_config = ConfigDict(extra="ignore")

    org_id: str
    goals: dict | None = None
    experience: str | None = None
    training_days: dict | None = None
    equipment: dict | None = None
    injuries: str | None = None
    nutrition: dict | None = None
    baseline: dict | None = None

    def missing_core_fields(self) -> list[str]:
        """Profile counts as complete when these three are filled (per spec)."""
        missing = []
        if not self.goals:
            missing.append("goals")
        if not self.experience:
            missing.append("experience")
        if not self.training_days:
            missing.append("training_days")
        return missing


class PlanDay(BaseModel):
    day: str
    session_type: Literal["run", "strength", "mobility", "rest"]
    description: str
    targets: dict = Field(default_factory=dict)


class PlanWeek(BaseModel):
    week_number: int
    focus: str = ""
    days: list[PlanDay]


class WorkoutPlan(BaseModel):
    """One row from workout_plans. weeks is jsonb in the DB."""

    model_config = ConfigDict(extra="ignore")

    id: str
    org_id: str
    status: str
    starts_on: str
    weeks: list[PlanWeek]
    rationale: str = ""


class WorkoutLog(BaseModel):
    """One row from workout_logs."""

    model_config = ConfigDict(extra="ignore")

    id: str
    org_id: str
    plan_id: str | None = None
    logged_date: str
    activity: Literal["run", "strength", "mobility", "rest", "other"]
    details: dict = Field(default_factory=dict)
    notes: str | None = None
