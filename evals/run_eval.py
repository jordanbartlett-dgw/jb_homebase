"""claw-eval: run Pydantic Evals datasets, compare to baseline, emit PostHog.

Usage:
    claw-eval run memory_recall
    claw-eval run obsidian_retrieval --save-baseline
    claw-eval run --all
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

import click
import logfire
import structlog
from pydantic_evals import Dataset
from pydantic_evals.reporting import EvaluationReport

from evals.registry import BASELINES_DIR, REGISTRY, REPORTS_DIR, EvalSpec
from jordan_claw.analytics import emitter
from jordan_claw.config import get_settings

log = structlog.get_logger()

REGRESSION_THRESHOLD = 0.05  # 5pp drop


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


def _load_baseline(name: str) -> dict | None:
    path = BASELINES_DIR / f"{name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _save_baseline(name: str, summary: RunSummary, git_sha: str | None) -> Path:
    path = BASELINES_DIR / f"{name}.json"
    payload = {
        "dataset": name,
        "score": summary.score,
        "ran_at": datetime.now(UTC).isoformat(),
        "git_sha": git_sha,
        "cases_total": summary.total_cases,
        "cases_passed": summary.passed_cases,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


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
    """Per-case scores arrive as {name: EvaluationResult}; flatten to floats."""
    out: dict[str, float] = {}
    for name, result in (case.scores or {}).items():
        value = getattr(result, "value", result)
        if isinstance(value, bool):
            value = 1.0 if value else 0.0
        if isinstance(value, (int, float)):
            out[name] = float(value)
    return out


def _passed(case_scores: dict[str, float], threshold: float = 0.5) -> bool:
    """A case 'passes' when the mean of its evaluator scores meets the threshold."""
    if not case_scores:
        return False
    return mean(case_scores.values()) >= threshold


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
    duration_ms: int,
    prev_score: float | None,
    regression: bool,
    experiment_name: str,
) -> dict[str, Any]:
    """Pure report-JSON builder — no I/O, so it's unit-testable without a CLI or logfire."""
    return {
        "dataset": dataset,
        "experiment_name": experiment_name,
        "ran_at": datetime.now(UTC).isoformat(),
        "score": score,
        "per_evaluator": per_evaluator,
        "total_cases": len(report.cases) + len(report.failures),
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


def _exit_code(summaries: list[RunSummary]) -> int:
    """Regression (exit 2) takes precedence over a bare task_fn failure (exit 1)."""
    if any(s.regression for s in summaries):
        return 2
    if any(s.failures for s in summaries):
        return 1
    return 0


async def _run_one(spec: EvalSpec) -> RunSummary:
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
        max_concurrency=4,
        progress=False,
    )
    duration_ms = int((time.monotonic() - start) * 1000)

    averages = report.averages()
    per_evaluator: dict[str, float] = dict(averages.scores) if averages else {}
    score = mean(per_evaluator.values()) if per_evaluator else 0.0
    passed_cases = sum(1 for c in report.cases if _passed(_case_score_floats(c)))
    total_cases = len(report.cases) + len(report.failures)

    baseline = _load_baseline(spec.name)
    prev_score = baseline.get("score") if baseline else None
    regression = prev_score is not None and score < prev_score - REGRESSION_THRESHOLD

    report_dict = _build_report_dict(
        dataset=spec.name,
        report=report,
        score=score,
        per_evaluator=per_evaluator,
        passed_cases=passed_cases,
        duration_ms=duration_ms,
        prev_score=prev_score,
        regression=regression,
        experiment_name=experiment_name,
    )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    report_path = REPORTS_DIR / f"{spec.name}_{ts}.json"
    report_path.write_text(json.dumps(report_dict, indent=2, default=str) + "\n")

    await emitter.eval_run_completed(
        dataset=spec.name,
        total_cases=total_cases,
        passed=passed_cases,
        score=score,
        prev_score=prev_score,
        regression=regression,
        duration_ms=duration_ms,
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
    )


def _print_summary(s: RunSummary) -> None:
    click.echo(f"\n[{s.dataset}]")
    click.echo(f"  score:        {s.score:.3f}")
    click.echo(f"  prev_score:   {s.prev_score if s.prev_score is not None else '—'}")
    click.echo(f"  regression:   {s.regression}")
    click.echo(f"  cases:        {s.passed_cases}/{s.total_cases}")
    click.echo(f"  duration:     {s.duration_ms} ms")
    for k, v in s.per_evaluator.items():
        click.echo(f"  - {k}: {v:.3f}")
    click.echo(f"  report:       {s.report_path}")


@click.group()
def cli() -> None:
    """claw-eval: run Pydantic Evals against Jordan Claw."""


@cli.command()
@click.argument("dataset", required=False)
@click.option("--all", "run_all", is_flag=True, help="Run every registered dataset.")
@click.option(
    "--save-baseline",
    is_flag=True,
    help="Persist the resulting score as the new regression baseline.",
)
def run(dataset: str | None, run_all: bool, save_baseline: bool) -> None:
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

    # A real tracer provider must exist even without a token — later agentic
    # evaluators need span-tree capture regardless of whether we ship to Logfire.
    # scrubbing=False: eval fixtures are synthetic, scrubbing mangles fixture text.
    if settings.logfire_token:
        logfire.configure(
            token=settings.logfire_token,
            send_to_logfire="if-token-present",
            service_name="claw-eval",
            environment="evals",
            scrubbing=False,
        )
    else:
        logfire.configure(
            send_to_logfire=False,
            service_name="claw-eval",
            environment="evals",
            scrubbing=False,
        )
    logfire.instrument_pydantic_ai()

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
        click.echo(f"Running {spec.name}…")
        summary = asyncio.run(_run_one(spec))
        summaries.append(summary)
        if save_baseline:
            path = _save_baseline(spec.name, summary, sha)
            click.echo(f"  baseline → {path}")
        _print_summary(summary)

    failed = [s for s in summaries if s.failures]
    for s in failed:
        for f in s.failures:
            click.echo(f"FAILURES ({len(s.failures)}): {f['name']}: {f['error_message']}", err=True)

    regressions = [s for s in summaries if s.regression]
    if regressions:
        names = ", ".join(s.dataset for s in regressions)
        click.echo(f"\nREGRESSION on: {names}", err=True)

    code = _exit_code(summaries)
    if code:
        raise SystemExit(code)


if __name__ == "__main__":
    cli()
