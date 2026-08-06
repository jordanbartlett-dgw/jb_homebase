# Weekly Schedule UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A weekly training view in the JB Homebase app: past days show logged workouts with a deterministic progressive-overload verdict, future days show planned sessions, served by a new `GET /app/workout/week` endpoint.

**Architecture:** Pure analysis functions in `src/jordan_claw/workout/analysis.py` (no I/O, never raise), a thin gateway loader in `src/jordan_claw/gateway/app_week.py` mounted in `main.py` beside `/app/today`, and a Flutter surface (`ThisWeekCard` on the dashboard + `WeekScheduleScreen` at `/home/training`) that mirrors the existing `today` feature files exactly.

**Tech Stack:** Python 3.12 / FastAPI / Pydantic v2 / supabase-py (backend); Flutter + Riverpod codegen + `http` package (frontend, NOT Dio — locked decision).

**Spec:** `docs/superpowers/specs/2026-08-06-weekly-schedule-ui-design.md`. Read it before starting any task.

## Global Constraints

- Branch: `feature/weekly-schedule-ui` (exists; spec already committed on it).
- `from __future__ import annotations` at the top of every Python file.
- Pydantic v2 only: `model_config = ConfigDict(...)`, never `class Config`.
- No new dependencies, Python or Dart.
- No DB schema changes. No migrations. Tables `workout_plans` / `workout_logs` are read as-is.
- No new agent tools: `tests/test_capabilities.py` and `tests/test_tool_registry.py` tool counts must NOT change.
- The analysis layer is total: it never raises on malformed data, it degrades to `no_baseline` with an honest reason.
- Named constants: `OVERLOAD_TOLERANCE = 0.03`, `BASELINE_LOOKBACK_DAYS = 45` in `analysis.py` only.
- Timezone: `America/Chicago` (`CENTRAL_TZ` from `jordan_claw.tools.calendar`).
- Python tests: `uv run pytest tests/<file> -v` (single files, never the full suite).
- Lint before every commit batch: `uv run ruff check . && uv run ruff format .`
- Flutter: after any `@Riverpod` change run `cd flutter_app && dart run build_runner build --delete-conflicting-outputs`, and commit the generated `.g.dart` output.
- Flutter tests live flat in `flutter_app/test/`.
- Commits: conventional (`feat:`, `test:`, `chore:`), trailer `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Push to `main` deploys production. Never push main; work stays on the feature branch until PR review.

---

### Task 1: Run overload analysis (`analysis.py` core)

**Files:**
- Create: `src/jordan_claw/workout/analysis.py`
- Test: `tests/test_workout_analysis.py`

**Interfaces:**
- Consumes: `WorkoutLog` from `jordan_claw.workout.models` (fields: `id`, `org_id`, `plan_id`, `logged_date: str` "YYYY-MM-DD", `activity`, `details: dict`, `notes`).
- Produces (later tasks rely on these exact names):
  - `Verdict = Literal["positive", "none", "negative", "no_baseline"]`
  - `class OverloadResult(BaseModel): verdict: Verdict; reason: str`
  - `judge_overload(log: WorkoutLog, all_logs: list[WorkoutLog]) -> OverloadResult | None` — returns `None` for `mobility`/`rest`/`other` (unscored); dispatches `run` and `strength`. `all_logs` is any list containing candidate baselines; the function itself filters to earlier-dated logs within `BASELINE_LOOKBACK_DAYS` of the log's own date.
  - Constants `OVERLOAD_TOLERANCE = 0.03`, `BASELINE_LOOKBACK_DAYS = 45`.

- [ ] **Step 1: Write the failing tests for run judging**

```python
# tests/test_workout_analysis.py
from __future__ import annotations

from jordan_claw.workout.analysis import judge_overload
from jordan_claw.workout.models import WorkoutLog


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_workout_analysis.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jordan_claw.workout.analysis'`

- [ ] **Step 3: Implement run judging**

```python
# src/jordan_claw/workout/analysis.py
from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel

from jordan_claw.workout.models import WorkoutLog

OVERLOAD_TOLERANCE = 0.03
BASELINE_LOOKBACK_DAYS = 45

Verdict = Literal["positive", "none", "negative", "no_baseline"]
_Cmp = Literal["better", "same", "worse"]


class OverloadResult(BaseModel):
    verdict: Verdict
    reason: str


def judge_overload(log: WorkoutLog, all_logs: list[WorkoutLog]) -> OverloadResult | None:
    """Score one logged workout against its baseline. None = unscored activity."""
    if log.activity == "run":
        return _judge_run(log, all_logs)
    if log.activity == "strength":
        return _judge_strength(log, all_logs)
    return None


def _log_date(log: WorkoutLog) -> date:
    return date.fromisoformat(log.logged_date)


def _baseline_candidates(log: WorkoutLog, all_logs: list[WorkoutLog]) -> list[WorkoutLog]:
    """Earlier logs of the same activity within the lookback, most recent first."""
    own = _log_date(log)
    floor = own - timedelta(days=BASELINE_LOOKBACK_DAYS)
    matches = [
        other
        for other in all_logs
        if other.id != log.id
        and other.activity == log.activity
        and floor <= _log_date(other) < own
    ]
    return sorted(matches, key=_log_date, reverse=True)


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _compare(current: float, previous: float, *, lower_is_better: bool = False) -> _Cmp:
    if previous == 0:
        return "same"
    delta = (current - previous) / previous
    if lower_is_better:
        delta = -delta
    if delta > OVERLOAD_TOLERANCE:
        return "better"
    if delta < -OVERLOAD_TOLERANCE:
        return "worse"
    return "same"


def _aggregate(comparisons: list[_Cmp]) -> Verdict:
    better = "better" in comparisons
    worse = "worse" in comparisons
    if better and not worse:
        return "positive"
    if worse and not better:
        return "negative"
    return "none"


def _vs(baseline: WorkoutLog) -> str:
    d = _log_date(baseline)
    return f"vs {d.strftime('%b')} {d.day}"


def _judge_run(log: WorkoutLog, all_logs: list[WorkoutLog]) -> OverloadResult:
    candidates = _baseline_candidates(log, all_logs)
    if not candidates:
        return OverloadResult(
            verdict="no_baseline",
            reason=f"no earlier run in the last {BASELINE_LOOKBACK_DAYS} days",
        )
    baseline = candidates[0]

    dist, prev_dist = _number(log.details.get("distance_mi")), _number(
        baseline.details.get("distance_mi")
    )
    dur, prev_dur = _number(log.details.get("duration_min")), _number(
        baseline.details.get("duration_min")
    )

    comparisons: list[_Cmp] = []
    parts: list[str] = []

    if dist is not None and prev_dist is not None:
        cmp = _compare(dist, prev_dist)
        comparisons.append(cmp)
        parts.append(f"{dist - prev_dist:+.1f} mi" if cmp != "same" else "same distance")
        if dur is not None and prev_dur is not None and dist > 0 and prev_dist > 0:
            pace_cmp = _compare(dur / dist, prev_dur / prev_dist, lower_is_better=True)
            comparisons.append(pace_cmp)
            parts.append(
                {"better": "faster pace", "same": "same pace", "worse": "slower pace"}[pace_cmp]
            )
    elif dur is not None and prev_dur is not None:
        cmp = _compare(dur, prev_dur)
        comparisons.append(cmp)
        parts.append(f"{dur - prev_dur:+.0f} min" if cmp != "same" else "same duration")

    if not comparisons:
        return OverloadResult(
            verdict="no_baseline",
            reason="run details missing comparable distance or duration",
        )
    return OverloadResult(
        verdict=_aggregate(comparisons),
        reason=f"{' at '.join(parts) if len(parts) == 2 else parts[0]} {_vs(baseline)}",
    )


def _judge_strength(log: WorkoutLog, all_logs: list[WorkoutLog]) -> OverloadResult:
    raise NotImplementedError  # Task 2
```

Note the run reason format: two parts join as `"+0.5 mi at same pace vs Jul 30"`, one part as `"+0.4 mi vs Jul 30"`. The tests in Step 1 assert substrings of this.

- [ ] **Step 4: Run tests to verify the run tests pass**

Run: `uv run pytest tests/test_workout_analysis.py -v`
Expected: all `test_run_*` and `test_unscored_*` PASS. (No strength tests exist yet.)

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check . && uv run ruff format .
git add src/jordan_claw/workout/analysis.py tests/test_workout_analysis.py
git commit -m "feat(workout): deterministic run overload analysis

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Strength overload analysis

**Files:**
- Modify: `src/jordan_claw/workout/analysis.py` (replace the `_judge_strength` stub)
- Test: `tests/test_workout_analysis.py` (append)

**Interfaces:**
- Consumes: everything Task 1 defined.
- Produces: working `_judge_strength`; `judge_overload` now fully functional. Per spec, each exercise matches against the most recent earlier strength log **containing that exercise** (split-routine safe), not just the single previous strength session.

- [ ] **Step 1: Write the failing strength tests**

Append to `tests/test_workout_analysis.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify the strength tests fail**

Run: `uv run pytest tests/test_workout_analysis.py -v -k strength`
Expected: FAIL with `NotImplementedError`

- [ ] **Step 3: Implement strength judging**

Replace the `_judge_strength` stub in `src/jordan_claw/workout/analysis.py`:

```python
class _Exercise(BaseModel):
    name: str
    weight: float | None = None
    reps: float | None = None
    sets: float | None = None


def _parse_exercises(details: dict) -> dict[str, _Exercise]:
    """Lenient parse of details['exercises'] into name -> stats. Empty on mess."""
    raw = details.get("exercises")
    entries: list[tuple[str, dict]] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                name = item.get("name") or item.get("exercise")
                if isinstance(name, str):
                    entries.append((name, item))
    elif isinstance(raw, dict):
        for name, stats in raw.items():
            if isinstance(name, str) and isinstance(stats, dict):
                entries.append((name, stats))

    parsed: dict[str, _Exercise] = {}
    for name, stats in entries:
        key = name.strip().lower()
        if not key:
            continue
        parsed[key] = _Exercise(
            name=key,
            weight=_number(stats.get("weight") or stats.get("weight_lb") or stats.get("lbs")),
            reps=_number(stats.get("reps")),
            sets=_number(stats.get("sets")),
        )
    return parsed


def _compare_exercise(current: _Exercise, previous: _Exercise) -> tuple[_Cmp, str] | None:
    """One exercise vs its baseline. None = not comparable (no shared numbers)."""
    if current.weight is not None and previous.weight is not None:
        if current.weight > previous.weight:
            return "better", f"{current.weight - previous.weight:+.0f} lb {current.name}"
        if current.weight < previous.weight:
            return "worse", f"{current.weight - previous.weight:+.0f} lb {current.name}"
        if current.reps is not None and previous.reps is not None and current.reps != previous.reps:
            delta = current.reps - previous.reps
            unit = "rep" if abs(delta) == 1 else "reps"
            return ("better" if delta > 0 else "worse", f"{delta:+.0f} {unit} {current.name}")
        return "same", f"same {current.name}"
    if current.reps is not None and previous.reps is not None:
        if current.reps == previous.reps:
            return "same", f"same {current.name}"
        delta = current.reps - previous.reps
        unit = "rep" if abs(delta) == 1 else "reps"
        return ("better" if delta > 0 else "worse", f"{delta:+.0f} {unit} {current.name}")
    return None


def _judge_strength(log: WorkoutLog, all_logs: list[WorkoutLog]) -> OverloadResult:
    current = _parse_exercises(log.details)
    if not current:
        return OverloadResult(
            verdict="no_baseline", reason="no parseable exercises in this session"
        )

    candidates = _baseline_candidates(log, all_logs)
    comparisons: list[_Cmp] = []
    parts: list[str] = []
    for name, exercise in current.items():
        for candidate in candidates:  # most recent first
            previous = _parse_exercises(candidate.details).get(name)
            if previous is None:
                continue
            compared = _compare_exercise(exercise, previous)
            if compared is None:
                continue
            cmp, phrase = compared
            comparisons.append(cmp)
            parts.append(f"{phrase} ({_vs(candidate)})")
            break

    if not comparisons:
        return OverloadResult(
            verdict="no_baseline",
            reason=f"no matching exercises in the last {BASELINE_LOOKBACK_DAYS} days",
        )
    return OverloadResult(verdict=_aggregate(comparisons), reason=", ".join(parts))
```

Note: `_Exercise` and helpers go ABOVE `_judge_strength` in the file. The reason format is `"+10 lb squat (vs Jul 29), -1 rep bench (vs Jul 27)"` — per-exercise baseline dates, matching the spec.

Wiring detail: the Task 1 tests assert `"+10 lb squat" in result.reason` and `"vs Jul 29" in result.reason` as substrings, so the parenthesized format satisfies them.

- [ ] **Step 4: Run the whole analysis test file**

Run: `uv run pytest tests/test_workout_analysis.py -v`
Expected: ALL PASS (runs + strength + unscored).

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check . && uv run ruff format .
git add src/jordan_claw/workout/analysis.py tests/test_workout_analysis.py
git commit -m "feat(workout): per-exercise strength overload analysis

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Week mapping (plan arithmetic + day status)

**Files:**
- Modify: `src/jordan_claw/workout/analysis.py` (append)
- Test: `tests/test_workout_analysis.py` (append)

**Interfaces:**
- Consumes: `WorkoutPlan`, `PlanDay`, `PlanWeek` from `jordan_claw.workout.models` (`PlanDay.day` is a weekday name like `"Monday"`; `plan.starts_on` is `"YYYY-MM-DD"`; `plan.weeks[i].days`).
- Produces (Task 4 relies on these exact names):
  - `planned_for_date(plan: WorkoutPlan | None, target: date) -> PlanDay | None`
  - `plan_status_for_week(plan: WorkoutPlan | None, week_start: date) -> Literal["active", "none", "ended"]`
  - `day_status(target: date, today: date, planned: PlanDay | None, has_logs: bool) -> DayStatus` where `DayStatus = Literal["logged", "missed", "rest", "upcoming", "today", "empty"]`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_workout_analysis.py`:

```python
from datetime import date

from jordan_claw.workout.analysis import day_status, plan_status_for_week, planned_for_date
from jordan_claw.workout.models import PlanDay, PlanWeek, WorkoutPlan


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_workout_analysis.py -v -k "planned or plan_status or day_status"`
Expected: FAIL with ImportError (names don't exist yet)

- [ ] **Step 3: Implement the mapping functions**

Append to `src/jordan_claw/workout/analysis.py` (extend the existing imports: add `PlanDay`, `WorkoutPlan` to the `jordan_claw.workout.models` import):

```python
DayStatus = Literal["logged", "missed", "rest", "upcoming", "today", "empty"]


def planned_for_date(plan: WorkoutPlan | None, target: date) -> PlanDay | None:
    """Pure arithmetic date -> PlanDay mapping. None outside the plan window."""
    if plan is None:
        return None
    starts = date.fromisoformat(plan.starts_on)
    offset = (target - starts).days
    if offset < 0:
        return None
    week_index = offset // 7
    if week_index >= len(plan.weeks):
        return None
    weekday_name = target.strftime("%A")
    for plan_day in plan.weeks[week_index].days:
        if plan_day.day.strip().lower() == weekday_name.lower():
            return plan_day
    return None


def plan_status_for_week(
    plan: WorkoutPlan | None, week_start: date
) -> Literal["active", "none", "ended"]:
    if plan is None:
        return "none"
    starts = date.fromisoformat(plan.starts_on)
    plan_end = starts + timedelta(days=7 * len(plan.weeks) - 1)
    if week_start > plan_end:
        return "ended"
    return "active"


def day_status(
    target: date, today: date, planned: PlanDay | None, *, has_logs: bool
) -> DayStatus:
    if has_logs:
        return "logged"
    if planned is None:
        return "empty"
    if planned.session_type == "rest":
        return "rest"
    if target == today:
        return "today"
    if target < today:
        return "missed"
    return "upcoming"
```

NOTE: `day_status` takes `has_logs` keyword-only — update the test calls accordingly (they already pass it by keyword).

- [ ] **Step 4: Run the whole analysis test file**

Run: `uv run pytest tests/test_workout_analysis.py -v`
Expected: ALL PASS

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check . && uv run ruff format .
git add src/jordan_claw/workout/analysis.py tests/test_workout_analysis.py
git commit -m "feat(workout): plan-to-date mapping and day status rules

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Gateway loader + response models (`app_week.py`)

**Files:**
- Create: `src/jordan_claw/gateway/app_week.py`
- Modify: `src/jordan_claw/db/workout.py` (append one query helper)
- Test: `tests/test_app_week.py`

**Interfaces:**
- Consumes: Tasks 1-3 (`judge_overload`, `planned_for_date`, `plan_status_for_week`, `day_status`, `DayStatus`, `Verdict`, `BASELINE_LOOKBACK_DAYS`), `get_active_plan` from `jordan_claw.db.workout`, `CENTRAL_TZ` from `jordan_claw.tools.calendar`.
- Produces (Task 5 and Flutter rely on these):
  - DB helper: `get_logs_since(client: AsyncClient, org_id: str, since_date: str) -> list[WorkoutLog]` (ascending `logged_date`)
  - `class WorkoutWeekResponse(BaseModel)` with fields `week_start: str`, `week_end: str`, `timezone: str`, `plan_status: Literal["active", "none", "ended"]`, `days: list[WeekDay]` (exactly 7, Monday first)
  - `class WeekDay(BaseModel)`: `date: str`, `is_today: bool`, `planned: PlannedSession | None`, `logs: list[LoggedWorkoutEntry]`, `day_status: DayStatus`
  - `class PlannedSession(BaseModel)`: `session_type: str`, `description: str`, `targets: dict`
  - `class LoggedWorkoutEntry(BaseModel)`: `id: str`, `activity: str`, `details: dict`, `notes: str | None`, `verdict: Verdict | None`, `reason: str | None`
  - `load_workout_week(db: AsyncClient, *, org_id: str, now: datetime | None = None) -> WorkoutWeekResponse`

- [ ] **Step 1: Append the DB helper (thin query, no dedicated test — convention for `db/` helpers; it's exercised via mocks in the loader tests and for real by the deploy-verify pass)**

Append to `src/jordan_claw/db/workout.py`:

```python
async def get_logs_since(
    client: AsyncClient,
    org_id: str,
    since_date: str,
) -> list[WorkoutLog]:
    """All logs on or after since_date (YYYY-MM-DD), oldest first."""
    result = (
        await client.table("workout_logs")
        .select("*")
        .eq("org_id", org_id)
        .gte("logged_date", since_date)
        .order("logged_date", desc=False)
        .execute()
    )
    return [WorkoutLog.model_validate(row) for row in result.data]
```

- [ ] **Step 2: Write the failing loader tests**

```python
# tests/test_app_week.py
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
    assert [d.date for d in response.days] == [
        f"2026-08-0{n}" for n in range(3, 10)
    ]

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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_app_week.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'jordan_claw.gateway.app_week'`

- [ ] **Step 4: Implement the loader**

```python
# src/jordan_claw/gateway/app_week.py
from __future__ import annotations

from datetime import date, datetime, timedelta
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
```

Unused import check: `date` is only used in type context here — drop it if ruff flags it.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_app_week.py -v`
Expected: ALL PASS

- [ ] **Step 6: Lint and commit**

```bash
uv run ruff check . && uv run ruff format .
git add src/jordan_claw/gateway/app_week.py src/jordan_claw/db/workout.py tests/test_app_week.py
git commit -m "feat(gateway): workout week loader with overload verdicts

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Route `GET /app/workout/week`

**Files:**
- Modify: `src/jordan_claw/main.py` (add import + route after the `/app/today` route, currently ending near line 456)
- Test: `tests/test_app_week.py` (append route tests)

**Interfaces:**
- Consumes: `load_workout_week`, `WorkoutWeekResponse` from Task 4; `_require_app_token` (already in `main.py`).
- Produces: `GET /app/workout/week`, bearer-authed with `CLAW_APP_TOKEN`, no query params.

- [ ] **Step 1: Write the failing route tests**

Append to `tests/test_app_week.py` (mirrors `tests/test_app_today.py` route tests):

```python
import httpx

from jordan_claw.gateway.app_week import WeekDay, WorkoutWeekResponse


def _client() -> httpx.AsyncClient:
    from jordan_claw.main import app

    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )


def _wire_app_state(app_token: str = "app-token") -> None:
    from jordan_claw.main import app

    settings = MagicMock()
    settings.claw_app_token = app_token
    settings.default_org_id = "org-1"
    app.state.settings = settings
    app.state.db = MagicMock()


async def test_week_route_requires_app_auth():
    _wire_app_state()
    async with _client() as client:
        response = await client.get(
            "/app/workout/week",
            headers={"Authorization": "Bearer wrong"},
        )
    assert response.status_code == 401


async def test_week_route_returns_structured_payload():
    from jordan_claw import main

    _wire_app_state()
    payload = WorkoutWeekResponse(
        week_start="2026-08-03",
        week_end="2026-08-09",
        timezone="America/Chicago",
        plan_status="active",
        days=[
            WeekDay(
                date=f"2026-08-0{n}",
                is_today=n == 6,
                planned=None,
                logs=[],
                day_status="empty",
            )
            for n in range(3, 10)
        ],
    )

    with patch.object(
        main, "load_workout_week", new=AsyncMock(return_value=payload)
    ) as loader:
        async with _client() as client:
            response = await client.get(
                "/app/workout/week",
                headers={"Authorization": "Bearer app-token"},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["week_start"] == "2026-08-03"
    assert body["plan_status"] == "active"
    assert len(body["days"]) == 7
    assert loader.await_args.kwargs["org_id"] == "org-1"
```

- [ ] **Step 2: Run tests to verify the route tests fail**

Run: `uv run pytest tests/test_app_week.py -v -k route`
Expected: FAIL with 404 (route not mounted)

- [ ] **Step 3: Mount the route**

In `src/jordan_claw/main.py`, add to the imports block (near the `app_today` import):

```python
from jordan_claw.gateway.app_week import WorkoutWeekResponse, load_workout_week
```

Add directly after the `app_today` route function:

```python
@app.get("/app/workout/week", response_model=WorkoutWeekResponse)
async def app_workout_week(request: Request) -> WorkoutWeekResponse:
    """Current Mon-Sun training week: plan ahead, logged workouts + overload
    verdicts behind. Pure DB reads, no agent run."""
    _require_app_token(request, surface="app workout week")
    return await load_workout_week(
        request.app.state.db,
        org_id=request.app.state.settings.default_org_id,
    )
```

- [ ] **Step 4: Run the full test file**

Run: `uv run pytest tests/test_app_week.py -v`
Expected: ALL PASS

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check . && uv run ruff format .
git add src/jordan_claw/main.py tests/test_app_week.py
git commit -m "feat(gateway): GET /app/workout/week route

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Flutter data layer (payloads, domain models, ApiClient, repository)

**Files:**
- Create: `flutter_app/lib/shared/api/workout_api_models.dart`
- Create: `flutter_app/lib/shared/models/workout_week.dart`
- Create: `flutter_app/lib/data/repositories/workout_week_repository.dart`
- Modify: `flutter_app/lib/shared/api/api_client.dart` (add `fetchWorkoutWeek`, import)
- Test: `flutter_app/test/workout_week_repository_test.dart`

**Interfaces:**
- Consumes: `ApiClient` internals (`_inner`, `_authorizationHeaders()`, `_decode`, `_timeout`, `baseUrl`) — follow `fetchToday` at `api_client.dart:294` exactly.
- Produces (Tasks 7-9 rely on these exact names):
  - Domain enums: `enum OverloadVerdict { positive, none, negative, noBaseline }`, `enum DayStatus { logged, missed, rest, upcoming, today, empty }`, `enum PlanStatus { active, none, ended }`
  - Domain models: `WorkoutWeek(weekStart, weekEnd, timezone, planStatus, days)`, `WorkoutDay(date, isToday, planned, logs, status)`, `PlannedSession(sessionType, description, targets)`, `LoggedWorkout(id, activity, details, notes, verdict, reason)` — `verdict`/`reason` nullable
  - `ApiClient.fetchWorkoutWeek() -> Future<WorkoutWeekPayload>`
  - `WorkoutWeekRepository(ApiClient).fetchWeek() -> Future<WorkoutWeek>`

- [ ] **Step 1: Write the payload models**

```dart
// flutter_app/lib/shared/api/workout_api_models.dart
class PlannedSessionPayload {
  const PlannedSessionPayload({
    required this.sessionType,
    required this.description,
    required this.targets,
  });

  factory PlannedSessionPayload.fromJson(Map<String, dynamic> json) {
    return PlannedSessionPayload(
      sessionType: json['session_type'] as String,
      description: json['description'] as String,
      targets: json['targets'] as Map<String, dynamic>? ?? const {},
    );
  }

  final String sessionType;
  final String description;
  final Map<String, dynamic> targets;
}

class LoggedWorkoutPayload {
  const LoggedWorkoutPayload({
    required this.id,
    required this.activity,
    required this.details,
    required this.notes,
    required this.verdict,
    required this.reason,
  });

  factory LoggedWorkoutPayload.fromJson(Map<String, dynamic> json) {
    return LoggedWorkoutPayload(
      id: json['id'] as String,
      activity: json['activity'] as String,
      details: json['details'] as Map<String, dynamic>? ?? const {},
      notes: json['notes'] as String?,
      verdict: json['verdict'] as String?,
      reason: json['reason'] as String?,
    );
  }

  final String id;
  final String activity;
  final Map<String, dynamic> details;
  final String? notes;
  final String? verdict;
  final String? reason;
}

class WorkoutDayPayload {
  const WorkoutDayPayload({
    required this.date,
    required this.isToday,
    required this.planned,
    required this.logs,
    required this.dayStatus,
  });

  factory WorkoutDayPayload.fromJson(Map<String, dynamic> json) {
    final plannedJson = json['planned'] as Map<String, dynamic>?;
    return WorkoutDayPayload(
      date: DateTime.parse(json['date'] as String),
      isToday: json['is_today'] as bool,
      planned: plannedJson == null ? null : PlannedSessionPayload.fromJson(plannedJson),
      logs: [
        for (final log in json['logs'] as List<dynamic>)
          LoggedWorkoutPayload.fromJson(log as Map<String, dynamic>),
      ],
      dayStatus: json['day_status'] as String,
    );
  }

  final DateTime date;
  final bool isToday;
  final PlannedSessionPayload? planned;
  final List<LoggedWorkoutPayload> logs;
  final String dayStatus;
}

class WorkoutWeekPayload {
  const WorkoutWeekPayload({
    required this.weekStart,
    required this.weekEnd,
    required this.timezone,
    required this.planStatus,
    required this.days,
  });

  factory WorkoutWeekPayload.fromJson(Map<String, dynamic> json) {
    return WorkoutWeekPayload(
      weekStart: DateTime.parse(json['week_start'] as String),
      weekEnd: DateTime.parse(json['week_end'] as String),
      timezone: json['timezone'] as String,
      planStatus: json['plan_status'] as String,
      days: [
        for (final day in json['days'] as List<dynamic>)
          WorkoutDayPayload.fromJson(day as Map<String, dynamic>),
      ],
    );
  }

  final DateTime weekStart;
  final DateTime weekEnd;
  final String timezone;
  final String planStatus;
  final List<WorkoutDayPayload> days;
}
```

- [ ] **Step 2: Write the domain models**

```dart
// flutter_app/lib/shared/models/workout_week.dart
import 'package:flutter/foundation.dart';

enum OverloadVerdict { positive, none, negative, noBaseline }

enum DayStatus { logged, missed, rest, upcoming, today, empty }

enum PlanStatus { active, none, ended }

@immutable
class PlannedSession {
  const PlannedSession({
    required this.sessionType,
    required this.description,
    required this.targets,
  });

  final String sessionType;
  final String description;
  final Map<String, dynamic> targets;
}

@immutable
class LoggedWorkout {
  const LoggedWorkout({
    required this.id,
    required this.activity,
    required this.details,
    required this.notes,
    required this.verdict,
    required this.reason,
  });

  final String id;
  final String activity;
  final Map<String, dynamic> details;
  final String? notes;
  final OverloadVerdict? verdict;
  final String? reason;
}

@immutable
class WorkoutDay {
  const WorkoutDay({
    required this.date,
    required this.isToday,
    required this.planned,
    required this.logs,
    required this.status,
  });

  final DateTime date;
  final bool isToday;
  final PlannedSession? planned;
  final List<LoggedWorkout> logs;
  final DayStatus status;
}

@immutable
class WorkoutWeek {
  const WorkoutWeek({
    required this.weekStart,
    required this.weekEnd,
    required this.timezone,
    required this.planStatus,
    required this.days,
  });

  final DateTime weekStart;
  final DateTime weekEnd;
  final String timezone;
  final PlanStatus planStatus;
  final List<WorkoutDay> days;

  WorkoutDay? get today {
    for (final day in days) {
      if (day.isToday) return day;
    }
    return null;
  }
}
```

- [ ] **Step 3: Add `fetchWorkoutWeek` to ApiClient**

In `flutter_app/lib/shared/api/api_client.dart`, add the import at the top with the others:

```dart
import 'workout_api_models.dart';
```

Add directly after `fetchToday`:

```dart
  /// GET /app/workout/week — current Mon-Sun training week with verdicts.
  Future<WorkoutWeekPayload> fetchWorkoutWeek() async {
    final uri = Uri.parse('$baseUrl/app/workout/week');
    final resp = await _inner.get(uri, headers: _authorizationHeaders()).timeout(_timeout);
    return WorkoutWeekPayload.fromJson(_decode(resp));
  }
```

- [ ] **Step 4: Write the repository (payload -> domain, enum parsing with safe fallbacks)**

```dart
// flutter_app/lib/data/repositories/workout_week_repository.dart
import '../../shared/api/api_client.dart';
import '../../shared/api/workout_api_models.dart';
import '../../shared/models/workout_week.dart';

class WorkoutWeekRepository {
  const WorkoutWeekRepository(this._apiClient);

  final ApiClient _apiClient;

  Future<WorkoutWeek> fetchWeek() async {
    final payload = await _apiClient.fetchWorkoutWeek();
    return WorkoutWeek(
      weekStart: payload.weekStart,
      weekEnd: payload.weekEnd,
      timezone: payload.timezone,
      planStatus: _planStatus(payload.planStatus),
      days: [for (final day in payload.days) _day(day)],
    );
  }

  WorkoutDay _day(WorkoutDayPayload payload) {
    final planned = payload.planned;
    return WorkoutDay(
      date: payload.date,
      isToday: payload.isToday,
      planned: planned == null
          ? null
          : PlannedSession(
              sessionType: planned.sessionType,
              description: planned.description,
              targets: planned.targets,
            ),
      logs: [
        for (final log in payload.logs)
          LoggedWorkout(
            id: log.id,
            activity: log.activity,
            details: log.details,
            notes: log.notes,
            verdict: _verdict(log.verdict),
            reason: log.reason,
          ),
      ],
      status: _dayStatus(payload.dayStatus),
    );
  }

  PlanStatus _planStatus(String raw) => switch (raw) {
        'active' => PlanStatus.active,
        'ended' => PlanStatus.ended,
        _ => PlanStatus.none,
      };

  DayStatus _dayStatus(String raw) => switch (raw) {
        'logged' => DayStatus.logged,
        'missed' => DayStatus.missed,
        'rest' => DayStatus.rest,
        'upcoming' => DayStatus.upcoming,
        'today' => DayStatus.today,
        _ => DayStatus.empty,
      };

  OverloadVerdict? _verdict(String? raw) => switch (raw) {
        'positive' => OverloadVerdict.positive,
        'none' => OverloadVerdict.none,
        'negative' => OverloadVerdict.negative,
        'no_baseline' => OverloadVerdict.noBaseline,
        _ => null,
      };
}
```

- [ ] **Step 5: Write the repository test**

Follow `flutter_app/test/today_repository_test.dart` for the mock-ApiClient pattern (it stubs `ApiClient` and asserts mapping). If that file uses a hand-rolled fake, copy the approach; the essential assertions:

```dart
// flutter_app/test/workout_week_repository_test.dart
import 'package:flutter_test/flutter_test.dart';
import 'package:jb_homebase/shared/api/workout_api_models.dart';

void main() {
  test('WorkoutWeekPayload parses the endpoint JSON shape', () {
    final payload = WorkoutWeekPayload.fromJson({
      'week_start': '2026-08-03',
      'week_end': '2026-08-09',
      'timezone': 'America/Chicago',
      'plan_status': 'active',
      'days': [
        {
          'date': '2026-08-03',
          'is_today': false,
          'planned': {
            'session_type': 'run',
            'description': 'easy run',
            'targets': {'distance_mi': 3},
          },
          'logs': [
            {
              'id': 'log-1',
              'activity': 'run',
              'details': {'distance_mi': 3.5},
              'notes': 'felt good',
              'verdict': 'positive',
              'reason': '+0.5 mi at same pace vs Jul 27',
            }
          ],
          'day_status': 'logged',
        },
        {
          'date': '2026-08-04',
          'is_today': true,
          'planned': null,
          'logs': [],
          'day_status': 'empty',
        },
      ],
    });

    expect(payload.planStatus, 'active');
    expect(payload.days, hasLength(2));
    expect(payload.days.first.planned!.sessionType, 'run');
    expect(payload.days.first.logs.single.verdict, 'positive');
    expect(payload.days[1].planned, isNull);
  });
}
```

Check the actual package name in `flutter_app/pubspec.yaml` (`name:` field) and use it in the import — the existing tests show the correct prefix.

Also verify unknown enum strings fall back safely: add a second test that maps a `WorkoutDayPayload` with `'day_status': 'something_new'` through `WorkoutWeekRepository._dayStatus` — since that's private, test it through `fetchWeek` with a faked `ApiClient` if `today_repository_test.dart` shows a fake-client pattern; otherwise settle for the payload test plus repository coverage in the widget test (Task 8's mock data goes through the domain models directly).

- [ ] **Step 6: Run the Flutter tests**

Run: `cd flutter_app && flutter test test/workout_week_repository_test.dart`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add flutter_app/lib/shared/api/workout_api_models.dart \
        flutter_app/lib/shared/models/workout_week.dart \
        flutter_app/lib/data/repositories/workout_week_repository.dart \
        flutter_app/lib/shared/api/api_client.dart \
        flutter_app/test/workout_week_repository_test.dart
git commit -m "feat(app): workout week data layer (payloads, models, repository)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Riverpod state + mock data

**Files:**
- Create: `flutter_app/lib/state/workout_week_state.dart` (+ generated `.g.dart`)
- Modify: `flutter_app/lib/shared/api/mock_data.dart` (add `workoutWeek` getter)

**Interfaces:**
- Consumes: `WorkoutWeekRepository` (Task 6), `apiClientProvider` from `state/core_providers.dart`, `GatewayConfig.isLive` from `shared/api/gateway_config.dart`, `MockData` pattern.
- Produces: `workoutWeekControllerProvider` (watch → `AsyncValue<WorkoutWeek>`), `WorkoutWeekController.refreshWeek()`, `MockData.workoutWeek`.

- [ ] **Step 1: Write the controller (mirror `today_state.dart` exactly)**

```dart
// flutter_app/lib/state/workout_week_state.dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

import '../data/repositories/workout_week_repository.dart';
import '../shared/api/gateway_config.dart';
import '../shared/api/mock_data.dart';
import '../shared/models/workout_week.dart';
import 'core_providers.dart';

part 'workout_week_state.g.dart';

final workoutWeekRepositoryProvider = Provider<WorkoutWeekRepository>((ref) {
  return WorkoutWeekRepository(ref.watch(apiClientProvider));
});

@Riverpod(keepAlive: true)
class WorkoutWeekController extends _$WorkoutWeekController {
  @override
  Future<WorkoutWeek> build() async {
    if (!GatewayConfig.isLive) return MockData.workoutWeek;
    return ref.read(workoutWeekRepositoryProvider).fetchWeek();
  }

  Future<void> refreshWeek() async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(build);
  }
}
```

- [ ] **Step 2: Add the mock week**

In `flutter_app/lib/shared/api/mock_data.dart`, add the import and a getter. The mock is date-relative so mock mode always shows a sensible current week:

```dart
import '../models/workout_week.dart';
```

```dart
  static WorkoutWeek get workoutWeek {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final monday = today.subtract(Duration(days: today.weekday - 1));
    final sessions = <int, PlannedSession>{
      0: const PlannedSession(sessionType: 'run', description: 'Easy run, 3 mi', targets: {}),
      2: const PlannedSession(sessionType: 'strength', description: 'Lower body', targets: {}),
      4: const PlannedSession(sessionType: 'run', description: 'Tempo run', targets: {}),
      5: const PlannedSession(sessionType: 'strength', description: 'Upper body', targets: {}),
      6: const PlannedSession(sessionType: 'rest', description: 'Rest day', targets: {}),
    };
    final days = <WorkoutDay>[];
    for (var offset = 0; offset < 7; offset++) {
      final date = monday.add(Duration(days: offset));
      final isToday = date == today;
      final planned = sessions[offset];
      final past = date.isBefore(today);
      List<LoggedWorkout> logs = const [];
      DayStatus status;
      if (past && planned != null && planned.sessionType != 'rest') {
        final positive = offset.isEven;
        logs = [
          LoggedWorkout(
            id: 'mock-log-$offset',
            activity: planned.sessionType,
            details: planned.sessionType == 'run'
                ? const {'distance_mi': 3.4, 'duration_min': 32}
                : const {
                    'exercises': [
                      {'name': 'squat', 'weight': 195, 'sets': 3, 'reps': 5},
                    ],
                  },
            notes: positive ? 'Felt strong.' : 'Tired today.',
            verdict: positive ? OverloadVerdict.positive : OverloadVerdict.negative,
            reason: positive ? '+0.4 mi at same pace vs last week' : '-5 lb squat vs last week',
          ),
        ];
        status = DayStatus.logged;
      } else if (planned == null) {
        status = DayStatus.empty;
      } else if (planned.sessionType == 'rest') {
        status = DayStatus.rest;
      } else if (isToday) {
        status = DayStatus.today;
      } else if (past) {
        status = DayStatus.missed;
      } else {
        status = DayStatus.upcoming;
      }
      days.add(WorkoutDay(
        date: date,
        isToday: isToday,
        planned: planned,
        logs: logs,
        status: status,
      ));
    }
    return WorkoutWeek(
      weekStart: monday,
      weekEnd: monday.add(const Duration(days: 6)),
      timezone: 'America/Chicago',
      planStatus: PlanStatus.active,
      days: days,
    );
  }
```

- [ ] **Step 3: Run codegen**

Run: `cd flutter_app && dart run build_runner build --delete-conflicting-outputs`
Expected: generates `lib/state/workout_week_state.g.dart` without errors.

- [ ] **Step 4: Analyze**

Run: `cd flutter_app && flutter analyze lib/state/workout_week_state.dart lib/shared/api/mock_data.dart`
Expected: No issues found.

- [ ] **Step 5: Commit (INCLUDE the generated file)**

```bash
git add flutter_app/lib/state/workout_week_state.dart \
        flutter_app/lib/state/workout_week_state.g.dart \
        flutter_app/lib/shared/api/mock_data.dart
git commit -m "feat(app): workout week controller and mock fixture

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: WeekScheduleScreen + route

**Files:**
- Create: `flutter_app/lib/features/home/week_schedule_screen.dart`
- Modify: `flutter_app/lib/routing/routes.dart` (add `training` constant)
- Modify: `flutter_app/lib/routing/app_router.dart` (register the route beside `calendar`)
- Test: `flutter_app/test/week_schedule_screen_test.dart`

**Interfaces:**
- Consumes: `workoutWeekControllerProvider` (Task 7), domain models (Task 6), theme (`AppTheme.pagePadding`, `AppTheme.radiusCard`, `theme.colorScheme`), `FadeSlideIn` widget.
- Produces: `WeekScheduleScreen` widget, `Routes.training = '/home/training'`. Verdict colors are exposed as `verdictColor(BuildContext, OverloadVerdict?)` — a top-level function in `week_schedule_screen.dart` — and reused by Task 9's card.

- [ ] **Step 1: Add the route constant**

In `flutter_app/lib/routing/routes.dart`, after the `calendar` line:

```dart
  static const String training = '/home/training';
```

- [ ] **Step 2: Write the screen**

```dart
// flutter_app/lib/features/home/week_schedule_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../shared/models/workout_week.dart';
import '../../shared/widgets/fade_slide_in.dart';
import '../../state/workout_week_state.dart';
import '../../theme/app_theme.dart';

/// Verdict tint shared by the week screen and the dashboard card.
Color verdictColor(BuildContext context, OverloadVerdict? verdict) {
  final scheme = Theme.of(context).colorScheme;
  final isDark = Theme.of(context).brightness == Brightness.dark;
  return switch (verdict) {
    OverloadVerdict.positive => isDark ? const Color(0xFF7FBF8E) : const Color(0xFF3E7A4E),
    OverloadVerdict.negative => scheme.error,
    OverloadVerdict.none || OverloadVerdict.noBaseline || null => scheme.onSurfaceVariant,
  };
}

String verdictLabel(OverloadVerdict verdict) => switch (verdict) {
      OverloadVerdict.positive => 'Overload +',
      OverloadVerdict.negative => 'Overload -',
      OverloadVerdict.none => 'Held steady',
      OverloadVerdict.noBaseline => 'No baseline',
    };

class WeekScheduleScreen extends ConsumerWidget {
  const WeekScheduleScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final week = ref.watch(workoutWeekControllerProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('This Week')),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: () => ref.read(workoutWeekControllerProvider.notifier).refreshWeek(),
          child: week.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (error, _) => ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: AppTheme.pagePadding,
              children: [
                const SizedBox(height: 80),
                Text(
                  'Couldn’t load this week’s training.',
                  textAlign: TextAlign.center,
                  style: theme.textTheme.titleMedium,
                ),
                const SizedBox(height: 12),
                Center(
                  child: OutlinedButton(
                    onPressed: () => ref.invalidate(workoutWeekControllerProvider),
                    child: const Text('Try again'),
                  ),
                ),
              ],
            ),
            data: (data) => ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: AppTheme.pagePadding.copyWith(top: 16, bottom: 40),
              children: [
                if (data.planStatus != PlanStatus.active)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 16),
                    child: _PlanNotice(status: data.planStatus),
                  ),
                for (final (index, day) in data.days.indexed)
                  FadeSlideIn(
                    delay: Duration(milliseconds: 40 * index),
                    child: Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: _DayTile(day: day),
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _PlanNotice extends StatelessWidget {
  const _PlanNotice({required this.status});

  final PlanStatus status;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final text = status == PlanStatus.ended
        ? 'Your plan has ended. Ask your coach for the next block.'
        : 'No active plan. Ask your coach to set one up.';
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(AppTheme.radiusCard),
        border: Border.all(color: theme.colorScheme.outlineVariant),
      ),
      child: Text(text, style: theme.textTheme.bodyMedium),
    );
  }
}

class _DayTile extends StatelessWidget {
  const _DayTile({required this.day});

  final WorkoutDay day;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final highlight = day.isToday;

    return Container(
      key: ValueKey('day-tile-${day.date.toIso8601String().substring(0, 10)}'),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(AppTheme.radiusCard),
        border: Border.all(
          color: highlight ? theme.colorScheme.primary : theme.colorScheme.outlineVariant,
          width: highlight ? 1.6 : 1,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                DateFormat('EEEE, MMM d').format(day.date).toUpperCase(),
                style: theme.textTheme.titleSmall,
              ),
              const Spacer(),
              _StatusChip(day: day),
            ],
          ),
          const SizedBox(height: 8),
          if (day.logs.isNotEmpty)
            for (final log in day.logs) _LogRow(log: log)
          else
            Text(
              switch (day.status) {
                DayStatus.missed => 'Missed: ${day.planned?.description ?? 'planned session'}',
                DayStatus.rest => 'Rest day',
                DayStatus.empty => 'Nothing planned',
                _ => day.planned?.description ?? 'Nothing planned',
              },
              style: theme.textTheme.bodyMedium,
            ),
        ],
      ),
    );
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.day});

  final WorkoutDay day;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final (label, color) = switch (day.status) {
      DayStatus.logged => ('LOGGED', verdictColor(context, day.logs.first.verdict)),
      DayStatus.missed => ('MISSED', theme.colorScheme.onSurfaceVariant),
      DayStatus.rest => ('REST', theme.colorScheme.onSurfaceVariant),
      DayStatus.upcoming => ('UPCOMING', theme.colorScheme.primary),
      DayStatus.today => ('TODAY', theme.colorScheme.primary),
      DayStatus.empty => ('—', theme.colorScheme.onSurfaceVariant),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(
        label,
        style: theme.textTheme.labelSmall?.copyWith(color: color),
      ),
    );
  }
}

class _LogRow extends StatelessWidget {
  const _LogRow({required this.log});

  final LoggedWorkout log;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final detail = log.details.entries
        .where((e) => e.value is num || e.value is String)
        .map((e) => '${e.key.replaceAll('_', ' ')}: ${e.value}')
        .join(' · ');

    return InkWell(
      onTap: () => _showDetail(context),
      borderRadius: BorderRadius.circular(8),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(log.activity.toUpperCase(), style: theme.textTheme.labelLarge),
            if (detail.isNotEmpty)
              Text(detail, style: theme.textTheme.bodySmall),
            if (log.verdict case final verdict?) ...[
              const SizedBox(height: 4),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    margin: const EdgeInsets.only(top: 5),
                    width: 8,
                    height: 8,
                    decoration: BoxDecoration(
                      color: verdictColor(context, verdict),
                      shape: BoxShape.circle,
                    ),
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      log.reason == null
                          ? verdictLabel(verdict)
                          : '${verdictLabel(verdict)} · ${log.reason}',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: verdictColor(context, verdict),
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }

  void _showDetail(BuildContext context) {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (sheetContext) {
        final theme = Theme.of(sheetContext);
        return Padding(
          padding: const EdgeInsets.fromLTRB(24, 0, 24, 40),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(log.activity.toUpperCase(), style: theme.textTheme.headlineSmall),
              const SizedBox(height: 12),
              for (final entry in log.details.entries)
                Text(
                  '${entry.key.replaceAll('_', ' ')}: ${entry.value}',
                  style: theme.textTheme.bodyMedium,
                ),
              if (log.reason case final reason?) ...[
                const SizedBox(height: 12),
                Text(
                  reason,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: verdictColor(sheetContext, log.verdict),
                  ),
                ),
              ],
              if (log.notes case final notes?) ...[
                const SizedBox(height: 12),
                Text(notes, style: theme.textTheme.bodyMedium),
              ],
            ],
          ),
        );
      },
    );
  }
}
```

- [ ] **Step 3: Register the route**

In `flutter_app/lib/routing/app_router.dart`: add the import

```dart
import '../features/home/week_schedule_screen.dart';
```

and inside the `Routes.home` GoRoute's `routes: [...]`, after the `'calendar'` entry (match the exact builder style used by the sibling `'calendar'` route — copy its wrapper/transition):

```dart
                  GoRoute(
                    path: 'training',
                    builder: (context, state) => const WeekScheduleScreen(),
                  ),
```

- [ ] **Step 4: Write the widget test**

Follow the harness style of `flutter_app/test/today_screen_test.dart` (ProviderScope overrides + pumpWidget). Core content:

```dart
// flutter_app/test/week_schedule_screen_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:jb_homebase/features/home/week_schedule_screen.dart';
import 'package:jb_homebase/shared/api/mock_data.dart';

void main() {
  testWidgets('renders 7 day tiles from the mock week', (tester) async {
    await tester.pumpWidget(
      const ProviderScope(
        child: MaterialApp(home: WeekScheduleScreen()),
      ),
    );
    await tester.pumpAndSettle();

    // Mock mode is the default in tests (GatewayConfig.isLive is false).
    final week = MockData.workoutWeek;
    expect(week.days, hasLength(7));
    for (final day in week.days) {
      expect(
        find.byKey(ValueKey(
          'day-tile-${day.date.toIso8601String().substring(0, 10)}',
        )),
        findsOneWidget,
      );
    }

    // At least one logged day shows a verdict line.
    expect(find.textContaining('Overload'), findsWidgets);
  });
}
```

Fix the package import prefix to match `pubspec.yaml` `name:` (same as Task 6). If `pumpAndSettle` times out on `FadeSlideIn` animations, use `await tester.pump(const Duration(seconds: 2))` instead — check how `today_screen_test.dart` handles it and copy that.

- [ ] **Step 5: Run analyze + the widget test**

Run: `cd flutter_app && flutter analyze && flutter test test/week_schedule_screen_test.dart`
Expected: analyze clean, test PASS

- [ ] **Step 6: Commit**

```bash
git add flutter_app/lib/features/home/week_schedule_screen.dart \
        flutter_app/lib/routing/routes.dart \
        flutter_app/lib/routing/app_router.dart \
        flutter_app/test/week_schedule_screen_test.dart
git commit -m "feat(app): weekly schedule screen at /home/training

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: ThisWeekCard on the dashboard

**Files:**
- Create: `flutter_app/lib/features/home/widgets/this_week_card.dart`
- Modify: `flutter_app/lib/features/home/dashboard_screen.dart` (insert card between UP NEXT calendar and UPDATES)
- Test: `flutter_app/test/this_week_card_test.dart`

**Interfaces:**
- Consumes: `workoutWeekControllerProvider`, domain models, `verdictColor` from `week_schedule_screen.dart`, `Routes.training`, `BouncyButton` from `shared/widgets/bouncy_button.dart`.
- Produces: `ThisWeekCard` widget (a `ConsumerWidget`, no constructor params).

- [ ] **Step 1: Write the card**

```dart
// flutter_app/lib/features/home/widgets/this_week_card.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../routing/routes.dart';
import '../../../shared/models/workout_week.dart';
import '../../../shared/widgets/bouncy_button.dart';
import '../../../state/workout_week_state.dart';
import '../../../theme/app_theme.dart';
import '../week_schedule_screen.dart';

/// Dashboard summary: today's session plus a 7-chip week strip.
class ThisWeekCard extends ConsumerWidget {
  const ThisWeekCard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final week = ref.watch(workoutWeekControllerProvider);

    return week.maybeWhen(
      data: (data) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('THIS WEEK', style: theme.textTheme.titleSmall),
          const SizedBox(height: 8),
          BouncyButton(
            onTap: () => context.push(Routes.training),
            child: Container(
              key: const ValueKey('this-week-card'),
              width: double.infinity,
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(
                color: theme.colorScheme.surface,
                borderRadius: BorderRadius.circular(AppTheme.radiusCard),
                border: Border.all(color: theme.colorScheme.outlineVariant),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(_headline(data), style: theme.textTheme.titleMedium),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      for (final day in data.days) ...[
                        Expanded(child: _DayChip(day: day)),
                        if (day != data.days.last) const SizedBox(width: 6),
                      ],
                    ],
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
      orElse: () => const SizedBox.shrink(),
    );
  }

  String _headline(WorkoutWeek data) {
    if (data.planStatus != PlanStatus.active) {
      return 'No active plan. Ask your coach.';
    }
    final today = data.today;
    final planned = today?.planned;
    if (planned == null || planned.sessionType == 'rest') {
      return planned == null ? 'Nothing planned today' : 'Rest day today';
    }
    return 'Today: ${planned.description}';
  }
}

class _DayChip extends StatelessWidget {
  const _DayChip({required this.day});

  final WorkoutDay day;

  static const _letters = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final letter = _letters[day.date.weekday - 1];
    final verdictTint = day.status == DayStatus.logged && day.logs.isNotEmpty
        ? verdictColor(context, day.logs.first.verdict)
        : null;

    final (background, border, foreground) = switch (day.status) {
      DayStatus.logged => (
          verdictTint!.withValues(alpha: 0.16),
          verdictTint,
          verdictTint,
        ),
      DayStatus.today || DayStatus.upcoming => (
          Colors.transparent,
          theme.colorScheme.primary,
          theme.colorScheme.primary,
        ),
      _ => (
          Colors.transparent,
          theme.colorScheme.outlineVariant,
          theme.colorScheme.onSurfaceVariant,
        ),
    };

    return Container(
      key: ValueKey('week-chip-${day.date.weekday}'),
      height: 34,
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: border,
          width: day.isToday ? 1.8 : 1,
        ),
      ),
      alignment: Alignment.center,
      child: Text(
        letter,
        style: theme.textTheme.labelMedium?.copyWith(color: foreground),
      ),
    );
  }
}
```

- [ ] **Step 2: Insert into the dashboard**

In `flutter_app/lib/features/home/dashboard_screen.dart`:

Add the import:

```dart
import 'widgets/this_week_card.dart';
```

In the `data:` branch of `today.when(...)`, after the `_UpcomingCalendar` FadeSlideIn block and BEFORE the `if (overview.artifacts.isNotEmpty)` block, insert:

```dart
                const SizedBox(height: 28),
                const FadeSlideIn(
                  delay: Duration(milliseconds: 240),
                  child: ThisWeekCard(),
                ),
```

- [ ] **Step 3: Write the card test**

```dart
// flutter_app/test/this_week_card_test.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:jb_homebase/features/home/widgets/this_week_card.dart';

void main() {
  testWidgets('shows the card with 7 chips in mock mode', (tester) async {
    await tester.pumpWidget(
      const ProviderScope(
        child: MaterialApp(home: Scaffold(body: ThisWeekCard())),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('this-week-card')), findsOneWidget);
    for (var weekday = 1; weekday <= 7; weekday++) {
      expect(find.byKey(ValueKey('week-chip-$weekday')), findsOneWidget);
    }
    expect(find.text('THIS WEEK'), findsOneWidget);
  });
}
```

Fix the package import prefix as in Tasks 6/8. The card navigates via `context.push` — the test doesn't tap it (no router in the harness), rendering assertions only.

- [ ] **Step 4: Run analyze + tests (card + regression on the dashboard tests)**

Run: `cd flutter_app && flutter analyze && flutter test test/this_week_card_test.dart test/today_screen_test.dart`
Expected: analyze clean, both PASS. If `today_screen_test.dart` pumps the full dashboard and now needs the workout provider, mock mode covers it (controller falls back to `MockData.workoutWeek` when not live) — but confirm it still passes.

- [ ] **Step 5: Commit**

```bash
git add flutter_app/lib/features/home/widgets/this_week_card.dart \
        flutter_app/lib/features/home/dashboard_screen.dart \
        flutter_app/test/this_week_card_test.dart
git commit -m "feat(app): This Week card on the dashboard

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 10: Verification sweep, prod-data sanity check, docs, PR

**Files:**
- Modify: `docs/architecture.md` (add `/app/workout/week` to the app-surface/module index — match the existing entry style for `/app/today`)

**Interfaces:** none new.

- [ ] **Step 1: Full changed-surface test run (backend)**

```bash
uv run pytest tests/test_workout_analysis.py tests/test_app_week.py tests/test_app_today.py -v
uv run ruff check . && uv run ruff format --check .
```

Expected: all pass, lint clean. (`test_app_today.py` guards against `main.py` regressions.)

- [ ] **Step 2: Full Flutter check**

```bash
cd flutter_app && flutter analyze && flutter test
```

Expected: clean. The Flutter suite is small; run all of it here since the app shell, router, and dashboard were touched.

- [ ] **Step 3: Prod-data sanity check of the analysis (requires Infisical auth)**

Jordan must first run `! infisical login` if the session is stale (it was on 2026-08-06). Then:

```bash
infisical run --env=dev -- uv run python - <<'EOF'
import asyncio, os
from supabase import acreate_client
from jordan_claw.gateway.app_week import load_workout_week

async def main():
    db = await acreate_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    week = await load_workout_week(db, org_id=os.environ["DEFAULT_ORG_ID"])
    for day in week.days:
        print(day.date, day.day_status, "planned:", day.planned.session_type if day.planned else "-")
        for log in day.logs:
            print("   ", log.activity, log.verdict, "|", log.reason)

asyncio.run(main())
EOF
```

Read the verdicts against the real logs. If real `details` rows use keys the parser misses (e.g. `distance_km`, exercises as prose), extend `_parse_exercises` / `_judge_run` leniently, add a test reproducing the real shape, and re-run. This is a READ-ONLY script; it writes nothing. If the env var name for the org id differs, check `src/jordan_claw/settings.py` for the actual field/alias and adjust.

- [ ] **Step 4: Update `docs/architecture.md`**

Find the section listing app endpoints (search for `/app/today`) and add `/app/workout/week` in the same style, pointing at `gateway/app_week.py` and `workout/analysis.py` with one-line descriptions. CLAUDE.md requires the system map stay current.

```bash
git add docs/architecture.md
git commit -m "docs(architecture): add /app/workout/week surface

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

- [ ] **Step 5: Push branch and open the PR**

```bash
git push -u origin feature/weekly-schedule-ui
gh pr create --title "feat: weekly schedule UI with progressive overload analysis" --body "$(cat <<'EOF'
## Summary
- GET /app/workout/week: current Mon-Sun training week — planned sessions ahead, logged workouts behind, each run/strength log scored for progressive overload (positive / none / negative / no_baseline) by deterministic pure functions (no LLM in the path)
- workout/analysis.py: run comparison (distance + pace, 3% tolerance), per-exercise strength comparison (split-routine safe, 45-day lookback), plan-date arithmetic, day statuses
- Flutter: This Week card on the dashboard + WeekScheduleScreen at /home/training, mirroring the today feature plumbing; mock mode fixture included

Spec: docs/superpowers/specs/2026-08-06-weekly-schedule-ui-design.md

## Test plan
- [ ] uv run pytest tests/test_workout_analysis.py tests/test_app_week.py -v
- [ ] cd flutter_app && flutter analyze && flutter test
- [ ] Prod read-only sanity check of verdicts against real workout_logs (plan Task 10 Step 3)
- [ ] After merge: deploy-verify skill — confirm new SHA live, curl /app/workout/week with the app token

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 6: Report**

Summarize: verdict examples from the prod sanity check, test counts, PR URL. Do NOT merge — Jordan reviews the PR. After merge, run the `deploy-verify` skill (push to main deploys production).

---

## Plan Self-Review Notes

Checked against the spec:

- Spec coverage: overload semantics (Tasks 1-2), week mapping + day statuses incl. `empty` (Task 3), endpoint contract (Tasks 4-5), ThisWeekCard + WeekScheduleScreen + mock mode (Tasks 6-9), error handling (loader tests + screen error states), testing (every task), out-of-scope respected (no paging, no agent tool, no /app/today changes, no migrations).
- Bottom-sheet detail on logged rows: implemented in `_LogRow._showDetail` (Task 8) — spec's "tap for full comparison" requirement.
- Type consistency: `judge_overload(log, all_logs)` used identically in Tasks 1, 2, 4; `day_status(target, today, planned, has_logs=...)` keyword-only everywhere; Flutter `verdictColor` defined in Task 8, consumed in Task 9; `Verdict`/`DayStatus` string values match between Python literals, JSON payloads, and Dart enum parsers (`no_baseline` → `noBaseline`).
- Known judgment call encoded: today-with-plan-and-no-log is `today`, not `missed`; today-no-plan-no-log is `empty`.
