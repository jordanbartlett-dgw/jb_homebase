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
        if other.id != log.id and other.activity == log.activity and floor <= _log_date(other) < own
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


def _judge_strength(log: WorkoutLog, all_logs: list[WorkoutLog]) -> OverloadResult:
    raise NotImplementedError  # Task 2
