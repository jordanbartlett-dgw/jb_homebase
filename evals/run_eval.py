"""claw-eval: run Pydantic Evals datasets, compare to baseline, emit PostHog.

Usage:
    claw-eval run memory_recall
    claw-eval run obsidian_retrieval --save-baseline
    claw-eval run --all
    claw-eval run memory_recall --json
    claw-eval list
    claw-eval compare memory_recall
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from statistics import mean
from typing import Any

import click
import logfire
import structlog
import yaml
from pydantic_evals import Dataset
from pydantic_evals.evaluators.llm_as_a_judge import set_default_judge_model
from pydantic_evals.reporting import EvaluationReport

from evals.registry import BASELINES_DIR, REGISTRY, REPORTS_DIR, EvalSpec
from jordan_claw.analytics import emitter
from jordan_claw.analytics.types import RunKind
from jordan_claw.config import get_settings
from jordan_claw.db.client import close_supabase_client, get_supabase_client
from jordan_claw.db.usage_events import save_usage_event
from jordan_claw.utils.pricing import compute_cost

log = structlog.get_logger()

REGRESSION_THRESHOLD = 0.05  # 5pp drop
REPORTS_KEEP = 60  # ~10 days of 6-dataset nightlies


@dataclass
class RunSummary:
    dataset: str
    score: float
    total_cases: int  # cases + failures — a task_fn exception must not vanish from the count
    passed_cases: int
    duration_ms: int
    prev_score: float | None
    regression: bool
    per_evaluator: dict[str, float]
    report_path: Path
    failures: list[dict[str, Any]]
    regression_reasons: list[str] = field(default_factory=list)
    cost_usd: float | None = None
    experiment_name: str = ""


def _load_baseline(name: str) -> dict | None:
    """Load a baseline file, normalizing v1 (no "schema" key) to the v2 internal shape.

    v2 files already have "composite"/"evaluators" keys and are returned as-is.
    v1 files only ever recorded a single composite "score" — normalized to
    {"composite": <score>, "evaluators": None, ...} so callers (in particular
    _detect_regression) only ever see one shape.
    """
    path = BASELINES_DIR / f"{name}.json"
    if not path.exists():
        return None
    raw = json.loads(path.read_text())
    if "schema" in raw:
        return raw
    return {
        "dataset": raw.get("dataset", name),
        "composite": raw["score"],
        "evaluators": None,
        "ran_at": raw.get("ran_at"),
        "git_sha": raw.get("git_sha"),
        "cases_total": raw.get("cases_total"),
        "cases_passed": raw.get("cases_passed"),
    }


def _save_baseline(name: str, summary: RunSummary, git_sha: str | None) -> Path:
    path = BASELINES_DIR / f"{name}.json"
    payload = {
        "schema": 2,
        "dataset": name,
        "ran_at": datetime.now(UTC).isoformat(),
        "git_sha": git_sha,
        "composite": summary.score,
        "evaluators": summary.per_evaluator,
        "cases_total": summary.total_cases,
        "cases_passed": summary.passed_cases,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def _prune_reports(reports_dir: Path, keep: int = REPORTS_KEEP) -> None:
    """Delete all but the newest `keep` report files in `reports_dir`.

    Only touches `*.json` files (report files); baselines and anything else in
    the directory are left alone. Filenames are `{dataset}_YYYYmmddTHHMMSSZ.json`,
    so lexicographic sort on the name is chronological order — no need to stat
    mtimes.
    """
    reports = sorted(reports_dir.glob("*.json"))
    for path in reports[:-keep] if keep > 0 else reports:
        path.unlink()


def _detect_regression(
    current_composite: float,
    current_evaluators: dict[str, float],
    baseline: dict | None,
) -> tuple[bool, list[str]]:
    """Compare a run's scores to its baseline (already normalized by _load_baseline).

    v2 baseline (evaluators is a dict): flags when the composite drops more
    than REGRESSION_THRESHOLD OR any evaluator present on BOTH sides drops
    more than a small-N-guarded threshold (see below). Evaluators present on
    only one side never flag — they're returned as informational reasons only
    (a scorer being added or removed is a code change, not a quality
    regression). TrajectoryMatch never flags regardless of drop size; a drop
    past the guarded threshold is still surfaced as an "info:"-prefixed
    reason so the CLI shows it without failing the run on it.

    v1 baseline (evaluators is None): composite-only, matching pre-v2 behavior.

    No baseline: never flags (first run establishing history).
    """
    if baseline is None:
        return False, []

    regression = False
    reasons: list[str] = []

    prev_composite = baseline["composite"]
    if current_composite < prev_composite - REGRESSION_THRESHOLD:
        regression = True
        reasons.append(
            f"composite: {current_composite:.3f} < {prev_composite:.3f} - {REGRESSION_THRESHOLD}"
        )

    prev_evaluators = baseline.get("evaluators")
    if prev_evaluators:
        # On small datasets, one flipped case moves a per-evaluator average by
        # more than the flat 5pp threshold on its own (e.g. 1/12 cases =
        # 8.3pp), so the flat threshold flags on a single case's worth of
        # judge noise. Per-run judge variance has been measured at up to
        # 7.5pp on this repo's datasets. Scaling the threshold to roughly two
        # flipped cases (1.5 / cases_total) requires two cases to flip before
        # flagging, which separates that noise from a real regression while
        # the flat 5pp floor still applies once the dataset is large enough
        # that 1.5/cases_total drops below it.
        cases_total = baseline.get("cases_total")
        evaluator_threshold = (
            max(REGRESSION_THRESHOLD, 1.5 / cases_total) if cases_total else REGRESSION_THRESHOLD
        )

        shared = set(current_evaluators) & set(prev_evaluators)
        for evaluator_name in sorted(shared):
            cur = current_evaluators[evaluator_name]
            prev = prev_evaluators[evaluator_name]
            if cur < prev - evaluator_threshold:
                reason = f"{evaluator_name}: {cur:.3f} < {prev:.3f} - {evaluator_threshold:.3f}"
                if evaluator_name == "TrajectoryMatch":
                    reasons.append(f"info: {reason}")
                else:
                    regression = True
                    reasons.append(reason)
        for evaluator_name in sorted(set(current_evaluators) - set(prev_evaluators)):
            reasons.append(f"new evaluator: {evaluator_name}")
        for evaluator_name in sorted(set(prev_evaluators) - set(current_evaluators)):
            reasons.append(f"missing evaluator: {evaluator_name}")

    return regression, reasons


def _git_sha() -> str | None:
    import subprocess

    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).parent.parent,
            stderr=subprocess.DEVNULL,
        )
        return out.decode().strip() or None
    except Exception:
        return None


def _case_score_floats(case) -> dict[str, float]:
    """Per-case scores arrive as {name: EvaluationResult}; flatten to floats.

    Reads both `case.scores` (numeric evaluators) and `case.assertions`
    (bool-valued evaluators). pydantic-evals routes any evaluator whose
    EvaluationReason.value is a bool into a separate `assertions` channel,
    never `scores` (see `_group_evaluator_outputs_by_type` in
    pydantic_evals.dataset) — this applies to ToolCorrectness and
    MaxToolCalls, which always return bool. Without reading assertions too,
    those evaluators would silently vanish from the composite, from
    per-case pass/fail, and from the baseline.
    """
    out: dict[str, float] = {}
    for group in (case.scores, case.assertions):
        for name, result in (group or {}).items():
            value = getattr(result, "value", result)
            if isinstance(value, bool):
                value = 1.0 if value else 0.0
            if isinstance(value, (int, float)):
                out[name] = float(value)
    return out


def _flat_evaluator_averages(cases: list[Any]) -> dict[str, float]:
    """Average every case's {name: float} scores (see `_case_score_floats`,
    scores + assertions) uniformly across `cases`.

    Equivalent to `report.averages().scores` under a uniform repeat count
    (every case runs the same number of times) — two-stage averaging
    (per-group, then across groups of equal size) equals a flat average
    over all runs. Used instead of `report.averages()` because that method
    only exposes `.scores`; `.assertions` is pooled into one blended float
    across every bool-valued evaluator, losing the per-evaluator-name
    breakdown this dict needs.
    """
    counts: dict[str, int] = defaultdict(int)
    sums: dict[str, float] = defaultdict(float)
    for case in cases:
        for name, value in _case_score_floats(case).items():
            counts[name] += 1
            sums[name] += value
    return {name: sums[name] / counts[name] for name in sums}


def _passed(case_scores: dict[str, float], threshold: float = 0.5) -> bool:
    """A case 'passes' when the mean of its evaluator scores meets the threshold."""
    if not case_scores:
        return False
    return mean(case_scores.values()) >= threshold


def _case_accounting(report: EvaluationReport) -> tuple[int, int]:
    """(passed_cases, total_cases) counted over SOURCE CASES, never raw runs.

    With repeat==1, pydantic-evals never sets `source_case_name`
    (ReportCase/ReportCaseFailure docstrings: "None when repeat == 1"), so
    `report.case_groups()` returns None and cases map 1:1 onto runs — fall
    back to the original run-level counting.

    With repeat>1, every run/failure carries the same `source_case_name`, so
    `case_groups()` (pydantic_evals/reporting/__init__.py) returns exactly
    one `ReportCaseGroup` per source case — a case that failed on every
    repeat still surfaces as a single group (runs=[], failures=[...]), so
    `len(groups)` is "source cases + failures", never inflated by the repeat
    count. Each group's `summary` is `ReportCaseAggregate.average(group.runs)`
    — the same per-case average that `report.averages()` re-averages across
    groups — so "passed" is judged against that averaged score, not any one
    run in isolation.
    """
    groups = report.case_groups()
    if groups is None:
        total = len(report.cases) + len(report.failures)
        passed = sum(1 for c in report.cases if _passed(_case_score_floats(c)))
        return passed, total

    total = len(groups)
    passed = sum(1 for g in groups if _passed(dict(g.summary.scores)))
    return passed, total


def _json_safe(value: Any) -> Any:
    """Best-effort JSON-safe coercion: keep value as-is if json.dumps accepts it."""
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return str(value)
    return value


def _case_results(case: Any) -> dict[str, dict[str, Any]]:
    """Flatten scores/labels/assertions into one {name: {value, reason}} dict."""
    out: dict[str, dict[str, Any]] = {}
    for group in (case.scores, case.labels, case.assertions):
        for name, result in (group or {}).items():
            out[name] = {"value": result.value, "reason": result.reason}
    return out


def _sum_metric(cases: list[Any], key: str) -> float | None:
    """Sum a metric across cases; None if no case reported it (vs. 0 if all reported 0)."""
    values = [c.metrics[key] for c in cases if key in (c.metrics or {})]
    if not values:
        return None
    return sum(values)


def _build_report_dict(
    *,
    dataset: str,
    report: EvaluationReport,
    score: float,
    per_evaluator: dict[str, float],
    passed_cases: int,
    total_cases: int,
    duration_ms: int,
    prev_score: float | None,
    regression: bool,
    experiment_name: str,
) -> dict[str, Any]:
    """Pure report-JSON builder — no I/O, so it's unit-testable without a CLI or logfire.

    total_cases/passed_cases are accepted as pre-computed inputs (via
    _case_accounting) rather than derived from report.cases/report.failures
    here, because under repeat>1 those lists hold one entry per RUN, not per
    source case — see _case_accounting's docstring.
    """
    return {
        "dataset": dataset,
        "experiment_name": experiment_name,
        "ran_at": datetime.now(UTC).isoformat(),
        "score": score,
        "per_evaluator": per_evaluator,
        "total_cases": total_cases,
        "passed_cases": passed_cases,
        "duration_ms": duration_ms,
        "prev_score": prev_score,
        "regression": regression,
        "input_tokens": _sum_metric(report.cases, "input_tokens"),
        "output_tokens": _sum_metric(report.cases, "output_tokens"),
        "cost_usd": _sum_metric(report.cases, "cost"),
        "failures": [
            {
                "name": f.name,
                "error_message": f.error_message,
                "trace_id": f.trace_id,
            }
            for f in report.failures
        ],
        "cases": [
            {
                "name": c.name,
                "inputs": _json_safe(c.inputs),
                "output": str(c.output)[:2000],
                "metrics": c.metrics,
                "attributes": c.attributes,
                "trace_id": c.trace_id,
                "scores": _case_score_floats(c),
                "results": _case_results(c),
                "task_duration": c.task_duration,
            }
            for c in report.cases
        ],
    }


def _usage_event_kwargs(
    *,
    spec: EvalSpec,
    report: EvaluationReport,
    duration_ms: int,
    org_id: str,
) -> dict[str, Any]:
    """Pure kwargs builder for the eval's usage_events row — unit-testable without I/O.

    cost_usd prefers the summed "cost" metric (from span attributes), but that
    metric is only set when Logfire prices the model — and obsidian_retrieval
    has no agent spans at all. Whenever no case reported a cost but tokens are
    known, fall back to our own price table so cost_usd isn't NULL for
    effectively every real run. Unknown models (e.g. the embeddings-only
    target) compute_cost() itself returns None for — a token-less eval run
    correctly stays cost_usd=None either way.
    """
    input_tokens = _sum_metric(report.cases, "input_tokens") or 0
    output_tokens = _sum_metric(report.cases, "output_tokens") or 0
    cost = _sum_metric(report.cases, "cost")
    if cost is not None:
        cost_usd: Decimal | None = Decimal(str(cost))
    elif input_tokens and output_tokens:
        cost_usd = compute_cost(spec.target_model, input_tokens, output_tokens)
    else:
        cost_usd = None
    return {
        "org_id": org_id,
        "agent_slug": f"eval:{spec.name}",
        "conversation_id": None,
        "channel": "eval",
        "run_kind": RunKind.EVAL,
        "schedule_name": None,
        "model": spec.target_model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
        "duration_ms": duration_ms,
        "tool_call_count": 0,
        "success": len(report.failures) == 0,
        "error_type": None,
        "error_severity": None,
        "trace_id": report.trace_id,
    }


def _exit_code(summaries: list[RunSummary]) -> int:
    """Regression (exit 2) takes precedence over a bare task_fn failure (exit 1)."""
    if any(s.regression for s in summaries):
        return 2
    if any(s.failures for s in summaries):
        return 1
    return 0


async def _run_one(spec: EvalSpec, *, repeat: int = 1, max_concurrency: int = 4) -> RunSummary:
    ds: Dataset[Any, Any, Any] = Dataset[spec.inputs_type, spec.expected_type, dict].from_file(
        spec.yaml_path,
        custom_evaluator_types=spec.custom_evaluators,
    )

    start = time.monotonic()
    experiment_name = f"{spec.name}@{_git_sha() or 'local'}"
    report = await ds.evaluate(
        spec.task_fn,
        name=experiment_name,
        metadata={"git_sha": _git_sha(), "dataset": spec.name},
        max_concurrency=max_concurrency,
        repeat=repeat,
        progress=False,
    )
    duration_ms = int((time.monotonic() - start) * 1000)

    per_evaluator: dict[str, float] = _flat_evaluator_averages(report.cases)
    score = mean(per_evaluator.values()) if per_evaluator else 0.0
    passed_cases, total_cases = _case_accounting(report)

    baseline = _load_baseline(spec.name)
    prev_score = baseline["composite"] if baseline else None
    regression, regression_reasons = _detect_regression(score, per_evaluator, baseline)

    report_dict = _build_report_dict(
        dataset=spec.name,
        report=report,
        score=score,
        per_evaluator=per_evaluator,
        passed_cases=passed_cases,
        total_cases=total_cases,
        duration_ms=duration_ms,
        prev_score=prev_score,
        regression=regression,
        experiment_name=experiment_name,
    )

    settings = get_settings()
    usage_kwargs = _usage_event_kwargs(
        spec=spec, report=report, duration_ms=duration_ms, org_id=settings.eval_test_org_id
    )
    cost_usd = usage_kwargs["cost_usd"]
    # The compute_cost fallback in _usage_event_kwargs is the resolved cost of
    # record — carry it into the report file too, not just the DB row.
    report_dict["cost_usd"] = float(cost_usd) if cost_usd is not None else None

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    report_path = REPORTS_DIR / f"{spec.name}_{ts}.json"
    report_path.write_text(json.dumps(report_dict, indent=2, default=str) + "\n")
    _prune_reports(REPORTS_DIR)

    client = await get_supabase_client(settings.supabase_url, settings.supabase_service_key)
    try:
        await save_usage_event(client, **usage_kwargs)
    finally:
        await close_supabase_client()

    await emitter.eval_run_completed(
        dataset=spec.name,
        total_cases=total_cases,
        passed=passed_cases,
        score=score,
        prev_score=prev_score,
        regression=regression,
        duration_ms=duration_ms,
        cost_usd=float(cost_usd) if cost_usd is not None else None,
        failures=len(report.failures),
    )
    await emitter.drain_pending_emits()

    return RunSummary(
        dataset=spec.name,
        score=score,
        total_cases=total_cases,
        passed_cases=passed_cases,
        duration_ms=duration_ms,
        prev_score=prev_score,
        regression=regression,
        per_evaluator=per_evaluator,
        report_path=report_path,
        failures=report_dict["failures"],
        regression_reasons=regression_reasons,
        cost_usd=report_dict["cost_usd"],
        experiment_name=experiment_name,
    )


def _print_summary(s: RunSummary, *, err: bool = False) -> None:
    """Human-readable summary. Written to stderr when --json keeps stdout machine-parseable."""
    click.echo(f"\n[{s.dataset}]", err=err)
    click.echo(f"  score:        {s.score:.3f}", err=err)
    click.echo(f"  prev_score:   {s.prev_score if s.prev_score is not None else '—'}", err=err)
    click.echo(f"  regression:   {s.regression}", err=err)
    for reason in s.regression_reasons:
        click.echo(f"    - {reason}", err=err)
    click.echo(f"  cases:        {s.passed_cases}/{s.total_cases}", err=err)
    click.echo(f"  duration:     {s.duration_ms} ms", err=err)
    for k, v in s.per_evaluator.items():
        click.echo(f"  - {k}: {v:.3f}", err=err)
    click.echo(f"  report:       {s.report_path}", err=err)


def _summary_json(s: RunSummary) -> dict[str, Any]:
    """Machine-readable summary for `--json` — same content as `_print_summary` plus
    cost_usd/failures/experiment_name. Pure, so it's unit-testable without a CLI process."""
    return {
        "dataset": s.dataset,
        "score": s.score,
        "prev_score": s.prev_score,
        "regression": s.regression,
        "regression_reasons": s.regression_reasons,
        "passed_cases": s.passed_cases,
        "total_cases": s.total_cases,
        "duration_ms": s.duration_ms,
        "per_evaluator": s.per_evaluator,
        "report_path": str(s.report_path),
        "cost_usd": s.cost_usd,
        "failures": s.failures,
        "experiment_name": s.experiment_name,
    }


def _format_table(headers: list[str], rows: list[list[str]]) -> str:
    """Minimal fixed-width table formatter — no dependency beyond stdlib."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def _fmt_row(cells: list[str]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

    lines = [_fmt_row(headers), _fmt_row(["-" * w for w in widths])]
    lines.extend(_fmt_row(row) for row in rows)
    return "\n".join(lines)


def _dataset_evaluator_names(yaml_data: dict[str, Any], spec: EvalSpec) -> list[str]:
    """Dataset-level evaluator names: the YAML's top-level `evaluators:` list plus any
    custom evaluator classes registered on the spec (custom scorers can be referenced only
    at case level, e.g. TriagePhraseScorer in email_triage.yaml, and would otherwise be
    invisible from the dataset-level YAML alone)."""
    names: list[str] = []
    for entry in yaml_data.get("evaluators") or []:
        if isinstance(entry, str):
            names.append(entry)
        elif isinstance(entry, dict):
            names.extend(entry.keys())
    for cls in spec.custom_evaluators:
        if cls.__name__ not in names:
            names.append(cls.__name__)
    return names


def _dataset_rows() -> list[list[str]]:
    """One row per REGISTRY dataset for `claw-eval list` — pure, no I/O beyond reading the
    dataset YAMLs and baseline files (no settings/API keys required)."""
    rows: list[list[str]] = []
    for spec in REGISTRY.values():
        yaml_data = yaml.safe_load(spec.yaml_path.read_text())
        case_count = len(yaml_data.get("cases") or [])
        evaluator_names = _dataset_evaluator_names(yaml_data, spec)
        baseline = _load_baseline(spec.name)
        composite = f"{baseline['composite']:.3f}" if baseline else "—"
        ran_at = (baseline.get("ran_at") if baseline else None) or "—"
        rows.append(
            [
                spec.name,
                str(case_count),
                ", ".join(evaluator_names),
                spec.target_model,
                composite,
                ran_at,
            ]
        )
    return rows


def _latest_report_pair(dataset: str) -> tuple[Path, Path]:
    """The two most recent report JSONs for `dataset`, oldest first.

    Filenames sort chronologically as-is (`{dataset}_YYYYmmddTHHMMSSZ.json`), so a plain
    lexical sort on the glob matches run order.
    """
    reports = sorted(REPORTS_DIR.glob(f"{dataset}_*.json"))
    if len(reports) < 2:
        raise click.ClickException(
            f"Need at least 2 reports for '{dataset}' to compare, found {len(reports)}."
        )
    return reports[-2], reports[-1]


def _report_delta(older: dict[str, Any], newer: dict[str, Any]) -> dict[str, Any]:
    """Pure delta computation between two report dicts — unit-testable without files."""
    older_ev = older.get("per_evaluator") or {}
    newer_ev = newer.get("per_evaluator") or {}
    per_evaluator = []
    for name in sorted(set(older_ev) | set(newer_ev)):
        o = older_ev.get(name)
        n = newer_ev.get(name)
        delta = (n - o) if (o is not None and n is not None) else None
        per_evaluator.append({"evaluator": name, "older": o, "newer": n, "delta": delta})

    composite_older = older.get("score")
    composite_newer = newer.get("score")
    composite_delta = (
        composite_newer - composite_older
        if (composite_older is not None and composite_newer is not None)
        else None
    )

    return {
        "per_evaluator": per_evaluator,
        "composite_older": composite_older,
        "composite_newer": composite_newer,
        "composite_delta": composite_delta,
        "cases_older": f"{older.get('passed_cases')}/{older.get('total_cases')}",
        "cases_newer": f"{newer.get('passed_cases')}/{newer.get('total_cases')}",
        "cost_older": older.get("cost_usd"),
        "cost_newer": newer.get("cost_usd"),
    }


@click.group()
def cli() -> None:
    """claw-eval: run Pydantic Evals against Jordan Claw."""


@cli.command(name="list")
def list_datasets() -> None:
    """List registered datasets: cases, evaluators, target model, baseline.

    Import-only — does not call get_settings(), so it works with no API keys configured.
    """
    headers = ["dataset", "cases", "evaluators", "target_model", "baseline", "ran_at"]
    click.echo(_format_table(headers, _dataset_rows()))


@cli.command()
@click.argument("dataset")
def compare(dataset: str) -> None:
    """Diff the two most recent reports/{dataset}_*.json reports.

    Import-only — does not call get_settings(), so it works with no API keys configured.
    """
    older_path, newer_path = _latest_report_pair(dataset)
    older = json.loads(older_path.read_text())
    newer = json.loads(newer_path.read_text())
    delta = _report_delta(older, newer)

    click.echo(f"[{dataset}] {older_path.name}  ->  {newer_path.name}\n")
    rows = [
        [
            r["evaluator"],
            f"{r['older']:.3f}" if r["older"] is not None else "—",
            f"{r['newer']:.3f}" if r["newer"] is not None else "—",
            f"{r['delta']:+.3f}" if r["delta"] is not None else "—",
        ]
        for r in delta["per_evaluator"]
    ]
    click.echo(_format_table(["evaluator", "older", "newer", "delta"], rows))

    composite_delta = delta["composite_delta"]
    click.echo(
        f"\ncomposite:  {delta['composite_older']:.3f} -> {delta['composite_newer']:.3f}"
        f"  ({composite_delta:+.3f})"
        if composite_delta is not None
        else f"\ncomposite:  {delta['composite_older']} -> {delta['composite_newer']}"
    )
    click.echo(f"cases:      {delta['cases_older']} -> {delta['cases_newer']}")
    click.echo(f"cost_usd:   {delta['cost_older']} -> {delta['cost_newer']}")


@cli.command()
@click.argument("dataset", required=False)
@click.option("--all", "run_all", is_flag=True, help="Run every registered dataset.")
@click.option(
    "--save-baseline",
    is_flag=True,
    help="Persist the resulting score as the new regression baseline.",
)
@click.option(
    "--repeat",
    type=click.IntRange(min=1),
    default=1,
    show_default=True,
    help="Run each case this many times; scores/pass counts aggregate per case, not per run.",
)
@click.option(
    "--concurrency",
    type=click.IntRange(min=1),
    default=4,
    show_default=True,
    help="Max concurrent case evaluations passed to Dataset.evaluate(max_concurrency=...).",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Print one JSON summary line per dataset to stdout. Human output moves to stderr.",
)
def run(
    dataset: str | None,
    run_all: bool,
    save_baseline: bool,
    repeat: int,
    concurrency: int,
    json_output: bool,
) -> None:
    if run_all and dataset:
        raise click.UsageError("Pass either a dataset name OR --all, not both.")
    if not run_all and not dataset:
        raise click.UsageError("Provide a dataset name or --all.")
    if run_all and save_baseline:
        raise click.UsageError("--save-baseline only works with a single dataset.")

    # Fail fast on missing env vars. Without this, get_settings() raises inside
    # each task and pydantic-evals silently drops the case, producing a phantom
    # 0/0 regression instead of a clear error.
    try:
        settings = get_settings()
    except Exception as e:
        raise click.ClickException(f"Settings invalid — check env vars:\n{e}") from e

    if json_output:
        # structlog's unconfigured default PrintLogger writes to stdout, which would
        # interleave operational log lines (e.g. posthog_client_initialized) with the
        # JSON summary lines below and break machine parsing.
        structlog.configure(logger_factory=structlog.PrintLoggerFactory(file=sys.stderr))

    # A real tracer provider must exist even without a token — later agentic
    # evaluators need span-tree capture regardless of whether we ship to Logfire.
    # scrubbing=False: eval fixtures are synthetic, scrubbing mangles fixture text.
    # console=False in --json mode: Logfire's default console span printer writes to
    # stdout, which would interleave with the JSON summary lines and break parsing.
    console = False if json_output else None
    if settings.logfire_token:
        logfire.configure(
            token=settings.logfire_token,
            send_to_logfire="if-token-present",
            service_name="claw-eval",
            environment="evals",
            scrubbing=False,
            console=console,
        )
    else:
        logfire.configure(
            send_to_logfire=False,
            service_name="claw-eval",
            environment="evals",
            scrubbing=False,
            console=console,
        )
    logfire.instrument_pydantic_ai()

    # Central judge model: LLMJudge configs in the dataset YAMLs carry no
    # `model:` key (see evals/datasets/*.yaml) and fall through to this default.
    set_default_judge_model(settings.eval_judge_model)

    targets: list[EvalSpec]
    if run_all:
        targets = list(REGISTRY.values())
    else:
        if dataset not in REGISTRY:
            known = ", ".join(REGISTRY)
            raise click.UsageError(f"Unknown dataset '{dataset}'. Known: {known}")
        targets = [REGISTRY[dataset]]

    summaries: list[RunSummary] = []
    sha = _git_sha()
    for spec in targets:
        click.echo(f"Running {spec.name}…", err=json_output)
        summary = asyncio.run(_run_one(spec, repeat=repeat, max_concurrency=concurrency))
        summaries.append(summary)
        if save_baseline:
            path = _save_baseline(spec.name, summary, sha)
            click.echo(f"  baseline → {path}", err=json_output)
        _print_summary(summary, err=json_output)
        if json_output:
            click.echo(json.dumps(_summary_json(summary)))

    failed = [s for s in summaries if s.failures]
    for s in failed:
        for f in s.failures:
            click.echo(f"FAILURES ({len(s.failures)}): {f['name']}: {f['error_message']}", err=True)

    regressions = [s for s in summaries if s.regression]
    if regressions:
        names = ", ".join(s.dataset for s in regressions)
        click.echo(f"\nREGRESSION on: {names}", err=True)
        for s in regressions:
            for reason in s.regression_reasons:
                click.echo(f"  [{s.dataset}] {reason}", err=True)

    code = _exit_code(summaries)
    if code:
        raise SystemExit(code)


if __name__ == "__main__":
    cli()
