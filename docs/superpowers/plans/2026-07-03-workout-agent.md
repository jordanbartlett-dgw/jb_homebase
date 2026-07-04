# Workout Coach Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A workout-coach agent in Jordan's org: structured intake of workout/nutrition preferences, persisted training plans, chat workout logging, a 6am daily-workout nudge, all reachable through a second Telegram bot.

**Architecture:** New `workout_profiles`/`workout_plans`/`workout_logs` tables plus six agent tools on BASE_TOOLSET. Intake behavior is prompt-driven. A second aiogram dispatcher in the same service handles the workout bot; Telegram chat IDs move from the org row to the agent row so the two bots don't stomp each other. The proactive scheduler gets a `{agent_slug: Bot}` map and a new `daily_workout` executor.

**Tech Stack:** Python 3.12, Pydantic AI (FunctionToolset), supabase-py async client, aiogram, croniter, pytest.

**Spec:** `docs/superpowers/specs/2026-07-03-workout-agent-design.md`

**Deployment-order constraint:** Migration 008 adds `agents.telegram_chat_id` and backfills it but does NOT drop `organizations.telegram_chat_id` (running prod code still uses it until the code deploy). Migration 009 drops the org column after the deploy is verified.

---

## File Structure

```
supabase/migrations/008_workout_tables.sql   new tables, agents.telegram_chat_id, workout-coach seed, schedule seed
supabase/migrations/009_drop_org_chat_id.sql post-deploy cleanup
src/jordan_claw/workout/__init__.py          empty package marker
src/jordan_claw/workout/models.py            WorkoutProfile, PlanDay, PlanWeek, WorkoutPlan, WorkoutLog
src/jordan_claw/db/workout.py                profile/plan/log queries
src/jordan_claw/tools/workout.py             six agent tools
src/jordan_claw/tools/__init__.py            register the six tools
src/jordan_claw/db/proactive.py              per-agent chat-id read/write
src/jordan_claw/channels/telegram.py         save chat id per agent
src/jordan_claw/proactive/delivery.py        chat lookup by agent_slug
src/jordan_claw/proactive/executors.py       execute_daily_workout
src/jordan_claw/proactive/scheduler.py       bots map, executor registration
src/jordan_claw/config.py                    workout bot settings
src/jordan_claw/main.py                      second dispatcher + bots map
tests/test_workout_models.py                 new
tests/test_db_workout.py                     new
tests/test_workout_tools.py                  new
tests/test_db_proactive.py                   update chat-id tests
tests/test_proactive_delivery.py             update chat lookup assertion
tests/test_proactive_executors.py            add daily_workout tests
tests/test_proactive_scheduler.py            update dispatch signature tests
```

---

### Task 1: Workout Pydantic models

**Files:**
- Create: `src/jordan_claw/workout/__init__.py` (empty)
- Create: `src/jordan_claw/workout/models.py`
- Test: `tests/test_workout_models.py`

- [ ] **Step 1: Write the failing tests**

```python
from __future__ import annotations

from jordan_claw.workout.models import (
    PlanDay,
    PlanWeek,
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
    log = WorkoutLog(
        id="l1", org_id="org-1", logged_date="2026-07-03", activity="run"
    )
    assert log.details == {}
    assert log.notes is None
    assert log.plan_id is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_workout_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jordan_claw.workout'`

- [ ] **Step 3: Write the models**

`src/jordan_claw/workout/__init__.py`: empty file.

`src/jordan_claw/workout/models.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_workout_models.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/jordan_claw/workout/ tests/test_workout_models.py
git commit -m "feat(workout): typed models for profile, plan, and logs"
```

---

### Task 2: DB layer for workout tables

**Files:**
- Create: `src/jordan_claw/db/workout.py`
- Test: `tests/test_db_workout.py`

Uses the `_mock_db` chained-query-builder pattern from `tests/test_db_memory.py`.

- [ ] **Step 1: Write the failing tests**

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from jordan_claw.db.workout import (
    get_active_plan,
    get_recent_workout_logs,
    get_workout_profile,
    insert_workout_log,
    save_workout_plan,
    upsert_workout_profile,
)
from jordan_claw.workout.models import PlanDay, PlanWeek

ORG_ID = "org-001"


def _mock_db(select_data=None):
    """Mock Supabase async client with chained query builder (same pattern as test_db_memory)."""
    mock_result = MagicMock(data=select_data or [])

    mock_query = MagicMock()
    mock_query.execute = AsyncMock(return_value=mock_result)
    mock_query.limit.return_value = mock_query
    mock_query.eq.return_value = mock_query
    mock_query.order.return_value = mock_query
    mock_query.select.return_value = mock_query
    mock_query.insert.return_value = mock_query
    mock_query.update.return_value = mock_query
    mock_query.upsert.return_value = mock_query

    mock_db = MagicMock()
    mock_db.table.return_value = mock_query
    return mock_db, mock_query


@pytest.mark.asyncio
async def test_get_workout_profile_none_when_missing():
    db, _ = _mock_db(select_data=[])
    assert await get_workout_profile(db, ORG_ID) is None


@pytest.mark.asyncio
async def test_get_workout_profile_returns_model():
    db, _ = _mock_db(select_data=[{"org_id": ORG_ID, "experience": "intermediate"}])
    profile = await get_workout_profile(db, ORG_ID)
    assert profile.experience == "intermediate"
    db.table.assert_called_with("workout_profiles")


@pytest.mark.asyncio
async def test_upsert_workout_profile_only_sends_provided_fields():
    db, query = _mock_db()
    await upsert_workout_profile(db, ORG_ID, experience="beginner")
    sent = query.upsert.call_args[0][0]
    assert sent["experience"] == "beginner"
    assert sent["org_id"] == ORG_ID
    assert "goals" not in sent
    assert query.upsert.call_args.kwargs["on_conflict"] == "org_id"


@pytest.mark.asyncio
async def test_get_active_plan_none_when_missing():
    db, _ = _mock_db(select_data=[])
    assert await get_active_plan(db, ORG_ID) is None


@pytest.mark.asyncio
async def test_get_active_plan_returns_model():
    db, query = _mock_db(select_data=[{
        "id": "p1", "org_id": ORG_ID, "status": "active",
        "starts_on": "2026-07-07", "weeks": [], "rationale": "Base",
    }])
    plan = await get_active_plan(db, ORG_ID)
    assert plan.status == "active"
    query.eq.assert_any_call("status", "active")


@pytest.mark.asyncio
async def test_save_workout_plan_archives_then_inserts():
    db, query = _mock_db(select_data=[{"id": "p2"}])
    weeks = [
        PlanWeek(
            week_number=1,
            days=[PlanDay(day="monday", session_type="run", description="Easy 4mi")],
        )
    ]
    row = await save_workout_plan(
        db, ORG_ID, starts_on="2026-07-07", weeks=weeks, rationale="Base"
    )
    assert row["id"] == "p2"
    query.update.assert_called_once_with({"status": "archived"})
    inserted = query.insert.call_args[0][0]
    assert inserted["weeks"][0]["days"][0]["session_type"] == "run"


@pytest.mark.asyncio
async def test_insert_workout_log():
    db, query = _mock_db(select_data=[{"id": "l1"}])
    await insert_workout_log(
        db, ORG_ID, logged_date="2026-07-03", activity="run",
        details={"distance_mi": 5}, notes="legs heavy",
    )
    sent = query.insert.call_args[0][0]
    assert sent["activity"] == "run"
    assert sent["details"] == {"distance_mi": 5}


@pytest.mark.asyncio
async def test_get_recent_workout_logs_ordered_desc():
    db, query = _mock_db(select_data=[
        {"id": "l1", "org_id": ORG_ID, "logged_date": "2026-07-02", "activity": "run"},
    ])
    logs = await get_recent_workout_logs(db, ORG_ID, limit=7)
    assert logs[0].activity == "run"
    query.order.assert_called_once_with("logged_date", desc=True)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_db_workout.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jordan_claw.db.workout'`

- [ ] **Step 3: Write the DB layer**

`src/jordan_claw/db/workout.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db_workout.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add src/jordan_claw/db/workout.py tests/test_db_workout.py
git commit -m "feat(workout): db layer for profiles, plans, and logs"
```

---

### Task 3: The six workout tools + registration

**Files:**
- Create: `src/jordan_claw/tools/workout.py`
- Modify: `src/jordan_claw/tools/__init__.py`
- Test: `tests/test_workout_tools.py`

Uses the `_make_ctx` MagicMock RunContext pattern from `tests/test_memory_tools.py`.

- [ ] **Step 1: Write the failing tests**

```python
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

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
    assert mock_insert.call_args.kwargs["logged_date"]  # today's date, non-empty
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


def test_tools_registered_on_base_toolset():
    from jordan_claw.tools import BASE_TOOLSET

    for name in (
        "get_workout_profile", "save_workout_profile", "get_workout_plan",
        "save_workout_plan", "log_workout", "get_recent_workouts",
    ):
        assert name in BASE_TOOLSET.tools
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_workout_tools.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jordan_claw.tools.workout'`

- [ ] **Step 3: Write the tools**

`src/jordan_claw/tools/workout.py`. Note the `_tool` suffix on two function names to avoid clashing with the db-layer imports; they register under the clean names.

```python
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
```

Append to `src/jordan_claw/tools/__init__.py` (imports join the existing block, registrations at the bottom):

```python
from jordan_claw.tools.workout import (
    get_recent_workouts,
    get_workout_plan,
    get_workout_profile_tool,
    log_workout,
    save_workout_plan_tool,
    save_workout_profile,
)

BASE_TOOLSET.add_function(get_workout_profile_tool, name="get_workout_profile")
BASE_TOOLSET.add_function(save_workout_profile, name="save_workout_profile")
BASE_TOOLSET.add_function(get_workout_plan, name="get_workout_plan")
BASE_TOOLSET.add_function(save_workout_plan_tool, name="save_workout_plan")
BASE_TOOLSET.add_function(log_workout, name="log_workout")
BASE_TOOLSET.add_function(get_recent_workouts, name="get_recent_workouts")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_workout_tools.py -v`
Expected: 8 passed

Also update the exhaustive tool-name whitelists in `tests/test_tool_registry.py` and `tests/test_agents.py` (registration tests assert exact set equality) to include the six new tool names, then run: `uv run pytest tests/test_agents.py tests/test_tool_registry.py -v`
Expected: all pass (registration didn't break tool filtering)

- [ ] **Step 5: Commit**

```bash
git add src/jordan_claw/tools/workout.py src/jordan_claw/tools/__init__.py tests/test_workout_tools.py
git commit -m "feat(workout): six workout tools registered on BASE_TOOLSET"
```

---

### Task 4: Per-agent Telegram chat IDs

**Files:**
- Modify: `src/jordan_claw/db/proactive.py:83-111` (get/save_telegram_chat_id)
- Modify: `src/jordan_claw/channels/telegram.py:135` (save call passes agent_slug)
- Modify: `src/jordan_claw/proactive/delivery.py:34` (lookup passes agent_slug)
- Test: `tests/test_db_proactive.py` (update 3 tests), `tests/test_proactive_delivery.py`

- [ ] **Step 1: Update the failing tests first**

In `tests/test_db_proactive.py`, replace the three chat-id tests:

```python
@pytest.mark.asyncio
async def test_get_telegram_chat_id_by_slug():
    from jordan_claw.db.proactive import get_telegram_chat_id

    db, query = _mock_db(select_data=[{"telegram_chat_id": 999}])
    chat_id = await get_telegram_chat_id(db, "org-1", agent_slug="workout-coach")
    assert chat_id == 999
    db.table.assert_called_with("agents")
    query.eq.assert_any_call("slug", "workout-coach")


@pytest.mark.asyncio
async def test_get_telegram_chat_id_falls_back_to_default_agent():
    from jordan_claw.db.proactive import get_telegram_chat_id

    db, query = _mock_db(select_data=[{"telegram_chat_id": 111}])
    chat_id = await get_telegram_chat_id(db, "org-1")
    assert chat_id == 111
    query.eq.assert_any_call("is_default", True)


@pytest.mark.asyncio
async def test_get_telegram_chat_id_not_set():
    from jordan_claw.db.proactive import get_telegram_chat_id

    db, _ = _mock_db(select_data=[])
    assert await get_telegram_chat_id(db, "org-1") is None


@pytest.mark.asyncio
async def test_save_telegram_chat_id_updates_agent_row():
    from jordan_claw.db.proactive import save_telegram_chat_id

    db, query = _mock_db()
    await save_telegram_chat_id(db, "org-1", "workout-coach", 12345)
    db.table.assert_called_with("agents")
    query.update.assert_called_once_with({"telegram_chat_id": 12345})
    query.eq.assert_any_call("slug", "workout-coach")
```

(Keep/reuse the file's existing `_mock_db` helper; if it lives only in `tests/test_db_memory.py`, copy it in as in Task 2.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_db_proactive.py -v`
Expected: FAIL (old signatures: `get_telegram_chat_id(db, org)` queries `organizations`, `save_telegram_chat_id(db, org, chat_id)` has no slug param)

- [ ] **Step 3: Implement**

Replace both functions in `src/jordan_claw/db/proactive.py`:

```python
async def get_telegram_chat_id(
    client: AsyncClient,
    org_id: str,
    agent_slug: str | None = None,
) -> int | None:
    """Look up the Telegram chat ID for an agent. Falls back to the org's
    default agent when no slug is given (memory-flag and legacy callers)."""
    query = (
        client.table("agents")
        .select("telegram_chat_id")
        .eq("org_id", org_id)
    )
    if agent_slug is not None:
        query = query.eq("slug", agent_slug)
    else:
        query = query.eq("is_default", True)
    result = await query.limit(1).execute()
    if not result.data:
        return None
    return result.data[0].get("telegram_chat_id")


async def save_telegram_chat_id(
    client: AsyncClient,
    org_id: str,
    agent_slug: str,
    chat_id: int,
) -> None:
    """Persist the Telegram chat ID on the agent row."""
    await (
        client.table("agents")
        .update({"telegram_chat_id": chat_id})
        .eq("org_id", org_id)
        .eq("slug", agent_slug)
        .execute()
    )
```

In `src/jordan_claw/channels/telegram.py`, the fire-and-forget save inside `handle_text` becomes:

```python
        asyncio.create_task(
            save_telegram_chat_id(db, default_org_id, agent_slug, message.chat.id),
            name=f"save-chat-id-{message.chat.id}",
        )
```

(`agent_slug` is already a parameter of `create_telegram_dispatcher`, captured by the closure.)

In `src/jordan_claw/proactive/delivery.py`, the lookup becomes:

```python
    chat_id = await get_telegram_chat_id(db, org_id, agent_slug)
```

(`agent_slug` is already a parameter of `send_proactive_message`; when None, the default-agent fallback applies, which is correct for memory-flag notifications.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db_proactive.py tests/test_proactive_delivery.py tests/test_proactive_integration.py -v`
Expected: all pass. If any delivery test asserts `get_telegram_chat_id` call args, update it to expect the third `agent_slug` argument.

- [ ] **Step 5: Commit**

```bash
git add src/jordan_claw/db/proactive.py src/jordan_claw/channels/telegram.py src/jordan_claw/proactive/delivery.py tests/test_db_proactive.py tests/test_proactive_delivery.py
git commit -m "feat(proactive): telegram chat ids keyed per agent, not per org"
```

---

### Task 5: daily_workout executor

**Files:**
- Modify: `src/jordan_claw/proactive/executors.py` (add prompt + executor)
- Modify: `src/jordan_claw/proactive/scheduler.py:28-33` (EXECUTOR_MAP entry)
- Test: `tests/test_proactive_executors.py` (add tests)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_proactive_executors.py` (reuse the file's existing settings fixture/mocks; `_plan()` helper as in Task 3's tests):

```python
@pytest.mark.asyncio
async def test_daily_workout_quiet_without_plan():
    from jordan_claw.proactive.executors import execute_daily_workout

    with patch("jordan_claw.proactive.executors.get_active_plan", return_value=None):
        result = await execute_daily_workout(
            MagicMock(), "org-1", {"agent_slug": "workout-coach"}, MagicMock()
        )
    assert result == ""


@pytest.mark.asyncio
async def test_daily_workout_composes_via_agent():
    from jordan_claw.proactive.executors import execute_daily_workout

    with (
        patch("jordan_claw.proactive.executors.get_active_plan", return_value=_plan()),
        patch("jordan_claw.proactive.executors.get_recent_workout_logs", return_value=[]),
        patch(
            "jordan_claw.proactive.executors._run_agent_prompt",
            return_value="Easy 4mi this morning.",
        ) as mock_run,
    ):
        result = await execute_daily_workout(
            MagicMock(), "org-1", {"agent_slug": "workout-coach"}, MagicMock()
        )
    assert result == "Easy 4mi this morning."
    assert mock_run.call_args.kwargs["schedule_name"] == "daily_workout"
    assert mock_run.call_args[0][2] == "workout-coach"  # agent_slug positional


@pytest.mark.asyncio
async def test_daily_workout_sentinel_suppresses_send():
    from jordan_claw.proactive.executors import execute_daily_workout

    with (
        patch("jordan_claw.proactive.executors.get_active_plan", return_value=_plan()),
        patch("jordan_claw.proactive.executors.get_recent_workout_logs", return_value=[]),
        patch(
            "jordan_claw.proactive.executors._run_agent_prompt",
            return_value="NOTHING_TO_SEND",
        ),
    ):
        result = await execute_daily_workout(
            MagicMock(), "org-1", {"agent_slug": "workout-coach"}, MagicMock()
        )
    assert result == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_proactive_executors.py -v -k daily_workout`
Expected: FAIL with `ImportError: cannot import name 'execute_daily_workout'`

- [ ] **Step 3: Implement the executor**

In `src/jordan_claw/proactive/executors.py`, add imports:

```python
from jordan_claw.db.workout import get_active_plan, get_recent_workout_logs
```

Add prompt constant and executor:

```python
DAILY_WORKOUT_PROMPT = """\
Compose today's workout message for Jordan. Find today's session in the plan.
Include:
1. Today's session with its targets
2. One line tying it to the goal or to recent logs
3. A nutrition note only if today's load warrants one

Keep it short. If today is a rest day and there is nothing worth saying,
reply with exactly NOTHING_TO_SEND.

## Today
{today}

## Active Plan
{plan}

## Recent Logs
{logs}
"""


async def execute_daily_workout(
    db: AsyncClient,
    org_id: str,
    config: dict,
    settings: Settings,
) -> str:
    """Compose the morning workout nudge from the active plan and recent logs."""
    plan = await get_active_plan(db, org_id)
    if plan is None:
        return ""

    tz_name = config.get("timezone", "America/Chicago")
    today = datetime.now(ZoneInfo(tz_name))

    logs = await get_recent_workout_logs(db, org_id, limit=7)
    logs_text = "\n".join(
        f"- [{log.logged_date}] {log.activity}: {log.notes or ''}" for log in logs
    ) or "No logged workouts."

    prompt = DAILY_WORKOUT_PROMPT.format(
        today=today.strftime("%A %Y-%m-%d"),
        plan=plan.model_dump_json(exclude={"org_id"}),
        logs=logs_text,
    )
    agent_slug = config.get("agent_slug", "workout-coach")
    content = await _run_agent_prompt(
        db, org_id, agent_slug, settings, prompt, schedule_name="daily_workout"
    )
    if "NOTHING_TO_SEND" in content:
        return ""
    return content
```

In `src/jordan_claw/proactive/scheduler.py`, add to imports and `EXECUTOR_MAP`:

```python
from jordan_claw.proactive.executors import (
    _parse_event_times,
    execute_calendar_reminder,
    execute_daily_scan,
    execute_daily_workout,
    execute_morning_briefing,
    execute_weekly_feedback_request,
    execute_weekly_review,
)

EXECUTOR_MAP = {
    "morning_briefing": execute_morning_briefing,
    "weekly_review": execute_weekly_review,
    "daily_scan": execute_daily_scan,
    "weekly_feedback_request": execute_weekly_feedback_request,
    "daily_workout": execute_daily_workout,
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_proactive_executors.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/jordan_claw/proactive/executors.py src/jordan_claw/proactive/scheduler.py tests/test_proactive_executors.py
git commit -m "feat(proactive): daily_workout executor with rest-day suppression"
```

---

### Task 6: Multi-bot scheduler dispatch

**Files:**
- Modify: `src/jordan_claw/proactive/scheduler.py:55-105,164-187` (dispatch_task, scheduler_loop)
- Modify: `src/jordan_claw/main.py:93-100` (pass bots map)
- Test: `tests/test_proactive_scheduler.py`

- [ ] **Step 1: Update the failing tests first**

In `tests/test_proactive_scheduler.py`, dispatch/scheduler tests currently pass a single `bot`. Update call sites to pass a bots dict and settings whose `default_agent_slug` is `"claw-main"`, and add:

```python
@pytest.mark.asyncio
async def test_dispatch_picks_bot_by_agent_slug():
    from jordan_claw.proactive.scheduler import dispatch_task

    claw_bot, workout_bot = AsyncMock(), AsyncMock()
    bots = {"claw-main": claw_bot, "workout-coach": workout_bot}
    schedule = _make_schedule(
        task_type="daily_workout", config={"agent_slug": "workout-coach"}
    )
    settings = MagicMock(default_agent_slug="claw-main")

    with (
        patch.dict(
            "jordan_claw.proactive.scheduler.EXECUTOR_MAP",
            {"daily_workout": AsyncMock(return_value="go run")},
        ),
        patch(
            "jordan_claw.proactive.scheduler.send_proactive_message"
        ) as mock_send,
        patch("jordan_claw.proactive.scheduler.update_last_run"),
    ):
        await dispatch_task(schedule, MagicMock(), bots, settings)

    assert mock_send.call_args.kwargs["bot"] is workout_bot


@pytest.mark.asyncio
async def test_dispatch_falls_back_to_default_bot():
    from jordan_claw.proactive.scheduler import dispatch_task

    claw_bot = AsyncMock()
    bots = {"claw-main": claw_bot}
    schedule = _make_schedule(
        task_type="daily_workout", config={"agent_slug": "workout-coach"}
    )
    settings = MagicMock(default_agent_slug="claw-main")

    with (
        patch.dict(
            "jordan_claw.proactive.scheduler.EXECUTOR_MAP",
            {"daily_workout": AsyncMock(return_value="go run")},
        ),
        patch(
            "jordan_claw.proactive.scheduler.send_proactive_message"
        ) as mock_send,
        patch("jordan_claw.proactive.scheduler.update_last_run"),
    ):
        await dispatch_task(schedule, MagicMock(), bots, settings)

    assert mock_send.call_args.kwargs["bot"] is claw_bot
```

(Use the file's existing schedule-factory helper; if it's named differently than `_make_schedule`, keep the file's name.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_proactive_scheduler.py -v`
Expected: FAIL (dispatch_task takes `bot`, not `bots`/`settings` in that order)

- [ ] **Step 3: Implement**

In `src/jordan_claw/proactive/scheduler.py`:

```python
async def dispatch_task(
    schedule: ProactiveSchedule,
    db: AsyncClient,
    bots: dict[str, Bot],
    settings: Settings,
) -> None:
    """Execute a scheduled task and send the result via the schedule's bot."""
    executor = EXECUTOR_MAP.get(schedule.task_type)
    if not executor:
        log.warning("proactive.unknown_task_type", task_type=schedule.task_type)
        return

    agent_slug = schedule.config.get("agent_slug", settings.default_agent_slug)
    bot = bots.get(agent_slug) or bots[settings.default_agent_slug]

    try:
        task_config = {**schedule.config, "timezone": schedule.timezone}
        content = await executor(db, schedule.org_id, task_config, settings)

        await send_proactive_message(
            bot=bot,
            db=db,
            org_id=schedule.org_id,
            content=content,
            task_type=schedule.task_type,
            trigger="scheduled",
            schedule_id=schedule.id,
            schedule_name=schedule.name,
            agent_slug=agent_slug,
            timezone=schedule.timezone,
        )
        ...  # rest of the function body unchanged (update_last_run,
             # calendar reminders after morning_briefing, logging)
```

The `...` above means: keep the existing body from `await update_last_run(...)` onward, unchanged; `schedule_calendar_reminders(db, schedule.org_id, reminder_config, settings, bot)` keeps receiving the resolved `bot`.

`scheduler_loop` signature and dispatch call become:

```python
async def scheduler_loop(
    db: AsyncClient,
    bots: dict[str, Bot],
    settings: Settings,
) -> None:
    ...
                    asyncio.create_task(
                        dispatch_task(schedule, db, bots, settings),
                        name=f"proactive-{schedule.task_type}-{schedule.id}",
                    )
```

In `src/jordan_claw/main.py`, replace the single-bot scheduler start:

```python
    bots: dict[str, Bot] = {settings.default_agent_slug: bot}

    # Start proactive messaging scheduler
    scheduler_task = asyncio.create_task(
        scheduler_loop(db, bots, settings),
        name="proactive-scheduler",
    )
```

(`bots` grows a second entry in Task 7.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_proactive_scheduler.py tests/test_proactive_integration.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/jordan_claw/proactive/scheduler.py src/jordan_claw/main.py tests/test_proactive_scheduler.py
git commit -m "feat(proactive): scheduler dispatches through per-agent bots"
```

---

### Task 7: Config + second dispatcher in main.py

**Files:**
- Modify: `src/jordan_claw/config.py:18` (two new settings)
- Modify: `src/jordan_claw/main.py:77-125` (second bot, polling task, shutdown)
- Test: `tests/test_config.py` (extend)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py` (follow the file's existing env-fixture pattern for required vars):

```python
def test_workout_bot_disabled_by_default(monkeypatch):
    # existing required env vars set by the file's fixture/helper
    settings = get_settings()
    assert settings.workout_telegram_bot_token == ""
    assert settings.workout_agent_slug == "workout-coach"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'workout_telegram_bot_token'`

- [ ] **Step 3: Implement**

`src/jordan_claw/config.py`, after `default_agent_slug`:

```python
    workout_telegram_bot_token: str = ""
    workout_agent_slug: str = "workout-coach"
```

`src/jordan_claw/main.py` lifespan, after the existing dispatcher is created and BEFORE `scheduler_task` is created (the scheduler must see the fully populated `bots` dict from Task 6):

```python
    # Start Telegram polling as background task
    polling_tasks = [asyncio.create_task(start_polling(bot, dp))]

    # Optional second bot: the workout coach
    workout_bot: Bot | None = None
    if settings.workout_telegram_bot_token:
        workout_bot = Bot(token=settings.workout_telegram_bot_token)
        workout_dp = create_telegram_dispatcher(
            workout_bot,
            db=db,
            default_org_id=settings.default_org_id,
            agent_slug=settings.workout_agent_slug,
            tavily_api_key=settings.tavily_api_key,
            fastmail_username=settings.fastmail_username,
            fastmail_app_password=settings.fastmail_app_password,
            openai_api_key=settings.openai_api_key,
            history_limit=settings.message_history_limit,
            environment=settings.environment,
        )
        bots[settings.workout_agent_slug] = workout_bot
        polling_tasks.append(asyncio.create_task(start_polling(workout_bot, workout_dp)))
        logger.info("workout_bot_started", agent_slug=settings.workout_agent_slug)
```

Shutdown block: cancel every polling task and close both sessions:

```python
    for task in polling_tasks:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    scheduler_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await scheduler_task
    await emitter.drain_pending_emits()
    shutdown_posthog()
    await bot.session.close()
    if workout_bot is not None:
        await workout_bot.session.close()
    await close_supabase_client()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: all pass

Run: `uv run python -c "from jordan_claw.main import app; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add src/jordan_claw/config.py src/jordan_claw/main.py tests/test_config.py
git commit -m "feat(gateway): optional second telegram dispatcher for workout coach"
```

---

### Task 8: Migration 008 (and 009)

**Files:**
- Create: `supabase/migrations/008_workout_tables.sql`
- Create: `supabase/migrations/009_drop_org_chat_id.sql`

- [ ] **Step 1: Write migration 008**

```sql
-- Workout coach: tables, per-agent chat ids, agent seed, schedule seed

-- Chat IDs move to agents (org column dropped in 009, after code deploy)
ALTER TABLE agents ADD COLUMN IF NOT EXISTS telegram_chat_id bigint;

UPDATE agents
SET telegram_chat_id = o.telegram_chat_id
FROM organizations o
WHERE agents.org_id = o.id
  AND agents.is_default = true
  AND agents.telegram_chat_id IS NULL;

-- Workout profile: one row per org, filled conversationally during intake
CREATE TABLE IF NOT EXISTS workout_profiles (
    org_id uuid PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
    goals jsonb,
    experience text,
    training_days jsonb,
    equipment jsonb,
    injuries text,
    nutrition jsonb,
    baseline jsonb,
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Training plans: one active per org
CREATE TABLE IF NOT EXISTS workout_plans (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    starts_on date NOT NULL,
    weeks jsonb NOT NULL DEFAULT '[]',
    rationale text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_workout_plans_one_active
    ON workout_plans (org_id) WHERE status = 'active';

-- Logged workouts
CREATE TABLE IF NOT EXISTS workout_logs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    plan_id uuid REFERENCES workout_plans(id),
    logged_date date NOT NULL,
    activity text NOT NULL CHECK (activity IN ('run', 'strength', 'mobility', 'rest', 'other')),
    details jsonb NOT NULL DEFAULT '{}',
    notes text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_workout_logs_org_date
    ON workout_logs (org_id, logged_date DESC);

ALTER TABLE workout_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE workout_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE workout_logs ENABLE ROW LEVEL SECURITY;

-- Seed the workout-coach agent (model matches claw-main's current model)
INSERT INTO agents (org_id, name, slug, system_prompt, model, tools)
SELECT
    '1408252a-fd36-4fd3-b527-3b2f495d7b9c',
    'Workout Coach',
    'workout-coach',
    'You are Jordan''s workout coach. You cover running, strength, mobility, and nutrition guidance.

Style: direct, short sentences, no jargon, no em dashes, no motivational filler. Talk like a coach who respects his athlete''s time.

At the start of every conversation, call get_workout_profile.
- If core fields are missing, you are in evaluation mode. Ask one question at a time. Cover in order: goals, current baseline (weekly mileage, key lifts), training days and time windows, equipment, injuries and constraints, nutrition preferences and restrictions. Save each answer with save_workout_profile as soon as you get it, so nothing is lost if the conversation drops.
- When the profile is complete and there is no active plan, propose a draft week-by-week plan covering running, strength, and mobility, with a short nutrition note. Give the reasoning in two or three sentences. Iterate until Jordan approves, then store it with save_workout_plan. Never save a plan Jordan has not approved.

When Jordan reports a completed workout, store it with log_workout immediately. Put numbers in details (distance_mi, duration_min, exercises) and how it felt in notes.

Before revising a plan, call get_recent_workouts. Adjust for what actually happened, not what was scheduled. If logs show a session keeps getting missed, move it instead of repeating it.

Calendar tools are available. Call current_datetime first to resolve relative dates. Check the calendar before proposing session times.

Never invent logged workouts or profile fields. If a tool fails, say so plainly and continue.',
    (SELECT model FROM agents WHERE slug = 'claw-main' LIMIT 1),
    '["current_datetime", "check_calendar", "schedule_event", "recall_memory", "get_workout_profile", "save_workout_profile", "get_workout_plan", "save_workout_plan", "log_workout", "get_recent_workouts"]'
WHERE NOT EXISTS (SELECT 1 FROM agents WHERE slug = 'workout-coach');

-- Seed the 6am daily nudge
INSERT INTO proactive_schedules (org_id, name, cron_expression, timezone, task_type, config)
VALUES (
    '1408252a-fd36-4fd3-b527-3b2f495d7b9c',
    'daily_workout',
    '0 6 * * *',
    'America/Chicago',
    'daily_workout',
    '{"agent_slug": "workout-coach"}'
)
ON CONFLICT (org_id, name) DO NOTHING;

-- Notify PostgREST to pick up new tables
SELECT pg_notify('pgrst', 'reload schema');
```

- [ ] **Step 2: Write migration 009** (applied only after the code deploy is verified)

```sql
-- Post-deploy cleanup: chat ids now live on agents (008 + code deploy)
ALTER TABLE organizations DROP COLUMN IF EXISTS telegram_chat_id;

SELECT pg_notify('pgrst', 'reload schema');
```

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/008_workout_tables.sql supabase/migrations/009_drop_org_chat_id.sql
git commit -m "feat(workout): migration 008 tables + seeds, 009 org chat-id cleanup"
```

---

### Task 9: Full verification + rollout

Ordering matters. 008 before deploy, 009 after.

- [ ] **Step 1: Targeted test sweep**

Run: `uv run pytest tests/test_workout_models.py tests/test_db_workout.py tests/test_workout_tools.py tests/test_db_proactive.py tests/test_proactive_delivery.py tests/test_proactive_executors.py tests/test_proactive_scheduler.py tests/test_proactive_integration.py tests/test_config.py tests/test_agents.py tests/test_gateway.py -q`
Expected: all pass

- [ ] **Step 2: Jordan creates the bot**

BotFather → `/newbot` → suggested name `@jb_workout_bot`. Jordan pastes the token into Railway as `WORKOUT_TELEGRAM_BOT_TOKEN` (service `jb_homebase`, project JB-HomeBase/production). Do NOT run interactive Railway CLI auth; Jordan does this in the dashboard or via `!` prefix.

- [ ] **Step 3: Apply migration 008**

Jordan runs `supabase/migrations/008_workout_tables.sql` in the Supabase SQL editor (project kmlzwhkbpouhzcyjujsn).

Verify with evidence (SQL editor):

```sql
SELECT slug, model, telegram_chat_id IS NOT NULL AS has_chat_id FROM agents;
SELECT name, cron_expression, task_type FROM proactive_schedules WHERE name = 'daily_workout';
SELECT count(*) FROM workout_profiles;
```

Expected: `claw-main` row with `has_chat_id = true`, new `workout-coach` row, one `daily_workout` schedule, count 0.

- [ ] **Step 4: Push and verify deploy**

```bash
git push origin main
```

Then use the deploy-verify skill: confirm the Railway deploy went green and `GET /health` returns `{"status": "ok"}`. Check Railway logs for `workout_bot_started`.

- [ ] **Step 5: Live smoke test**

Jordan sends `/start` then a first message to @jb_workout_bot. Expected: the coach begins the evaluation (asks about goals). Verify with evidence:

```sql
SELECT org_id, goals, experience FROM workout_profiles;
SELECT telegram_chat_id FROM agents WHERE slug = 'workout-coach';
```

Expected: profile row appears as intake progresses; workout-coach chat id set. Also confirm claw-main bot still responds normally.

- [ ] **Step 6: Apply migration 009**

Only after Step 5 passes. Jordan runs 009 in the SQL editor. Verify:

```sql
SELECT column_name FROM information_schema.columns
WHERE table_name = 'organizations' AND column_name = 'telegram_chat_id';
```

Expected: zero rows.

- [ ] **Step 7: Update memory + docs**

Update auto-memory (`project_jordan_claw_phase1.md`: tool count, second bot; `project_phase2_deferred_decisions.md`: note chat-id-per-agent shipped, routing still deferred). Commit any doc updates.
