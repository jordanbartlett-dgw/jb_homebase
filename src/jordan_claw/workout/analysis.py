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


def _safe_log_date(log: WorkoutLog) -> date | None:
    """Parse logged_date safely, returning None if unparseable."""
    try:
        return date.fromisoformat(log.logged_date)
    except ValueError:
        return None


def _log_date(log: WorkoutLog) -> date:
    return date.fromisoformat(log.logged_date)


def _baseline_candidates(log: WorkoutLog, all_logs: list[WorkoutLog]) -> list[WorkoutLog]:
    """Earlier logs of the same activity within the lookback, most recent first."""
    own = _safe_log_date(log)
    if own is None:
        return []
    floor = own - timedelta(days=BASELINE_LOOKBACK_DAYS)
    matches = []
    for other in all_logs:
        if other.id == log.id or other.activity != log.activity:
            continue
        other_date = _safe_log_date(other)
        if other_date is None:
            continue
        if floor <= other_date < own:
            matches.append(other)
    return sorted(matches, key=lambda x: _safe_log_date(x) or date.min, reverse=True)


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
    if _safe_log_date(log) is None:
        return OverloadResult(
            verdict="no_baseline",
            reason="unreadable workout date",
        )
    candidates = _baseline_candidates(log, all_logs)
    if not candidates:
        return OverloadResult(
            verdict="no_baseline",
            reason=f"no earlier run in the last {BASELINE_LOOKBACK_DAYS} days",
        )
    baseline = candidates[0]

    dist, prev_dist = (
        _number(log.details.get("distance_mi")),
        _number(baseline.details.get("distance_mi")),
    )
    dur, prev_dur = (
        _number(log.details.get("duration_min")),
        _number(baseline.details.get("duration_min")),
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


class _Exercise(BaseModel):
    name: str
    weight: float | None = None
    reps: float | None = None
    sets: float | None = None


def _first_number(stats: dict, *keys: str) -> float | None:
    """Return the first non-None numeric value from stats for the given keys."""
    for key in keys:
        value = _number(stats.get(key))
        if value is not None:
            return value
    return None


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
            weight=_first_number(stats, "weight", "weight_lb", "lbs"),
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
