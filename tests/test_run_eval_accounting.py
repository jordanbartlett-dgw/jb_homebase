"""Unit tests for the eval run's usage_events accounting.

Fabricated ReportCase/EvalSpec-shaped objects only (SimpleNamespace) — no live
API calls, no live Supabase. Mirrors the _mock_db style from
tests/test_agent_runner.py for the insert-payload assertion.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from evals.run_eval import _usage_event_kwargs
from jordan_claw.analytics.types import RunKind
from jordan_claw.db.usage_events import save_usage_event

ORG_ID = "eaa1eaa1-eaa1-eaa1-eaa1-eaa1eaa1eaa1"


def _mock_db():
    query = MagicMock()
    query.execute = AsyncMock(return_value=MagicMock(data=[{"id": "u1"}]))
    query.insert.return_value = query
    db = MagicMock()
    db.table.return_value = query
    return db, query


def _case(**metrics: float) -> SimpleNamespace:
    return SimpleNamespace(metrics=metrics)


def _spec(name: str, target_model: str) -> SimpleNamespace:
    return SimpleNamespace(name=name, target_model=target_model)


def _report(cases: list, failures: list, trace_id: str | None = "trace-abc") -> SimpleNamespace:
    return SimpleNamespace(cases=cases, failures=failures, trace_id=trace_id)


def test_usage_event_kwargs_sums_tokens_and_cost():
    spec = _spec("memory_recall", "anthropic:claude-sonnet-4-5-20250929")
    report = _report(
        cases=[
            _case(input_tokens=100, output_tokens=50, cost=0.01),
            _case(input_tokens=200, output_tokens=75, cost=0.02),
        ],
        failures=[],
    )

    kwargs = _usage_event_kwargs(spec=spec, report=report, duration_ms=1234, org_id=ORG_ID)

    assert kwargs["org_id"] == ORG_ID
    assert kwargs["agent_slug"] == "eval:memory_recall"
    assert kwargs["conversation_id"] is None
    assert kwargs["channel"] == "eval"
    assert kwargs["run_kind"] == RunKind.EVAL
    assert kwargs["schedule_name"] is None
    assert kwargs["model"] == "anthropic:claude-sonnet-4-5-20250929"
    assert kwargs["input_tokens"] == 300
    assert kwargs["output_tokens"] == 125
    assert kwargs["cost_usd"] == Decimal("0.03")
    assert isinstance(kwargs["cost_usd"], Decimal)
    assert kwargs["duration_ms"] == 1234
    assert kwargs["tool_call_count"] == 0
    assert kwargs["success"] is True
    assert kwargs["error_type"] is None
    assert kwargs["error_severity"] is None
    assert kwargs["trace_id"] == "trace-abc"


def test_usage_event_kwargs_success_false_when_report_has_failures():
    spec = _spec("med_check", "anthropic:claude-sonnet-5")
    report = _report(
        cases=[_case(input_tokens=10, output_tokens=5)],
        failures=[SimpleNamespace(name="broke", error_message="boom", trace_id="trace-fail")],
    )

    kwargs = _usage_event_kwargs(spec=spec, report=report, duration_ms=1, org_id=ORG_ID)

    assert kwargs["success"] is False


def test_usage_event_kwargs_cost_none_when_no_cost_metric_reported():
    spec = _spec("obsidian_retrieval", "openai:text-embedding-3-small")
    report = _report(
        cases=[_case(input_tokens=10, output_tokens=0), _case(input_tokens=20, output_tokens=0)],
        failures=[],
    )

    kwargs = _usage_event_kwargs(spec=spec, report=report, duration_ms=1, org_id=ORG_ID)

    assert kwargs["cost_usd"] is None
    assert kwargs["input_tokens"] == 30
    assert kwargs["output_tokens"] == 0


def test_usage_event_kwargs_zero_tokens_when_no_cases_report_metrics():
    """No case reported input_tokens/output_tokens at all — the row still gets 0, not None."""
    spec = _spec("obsidian_retrieval", "openai:text-embedding-3-small")
    report = _report(cases=[_case()], failures=[])

    kwargs = _usage_event_kwargs(spec=spec, report=report, duration_ms=1, org_id=ORG_ID)

    assert kwargs["input_tokens"] == 0
    assert kwargs["output_tokens"] == 0
    assert kwargs["cost_usd"] is None


@pytest.mark.asyncio
async def test_save_usage_event_inserts_built_kwargs_row():
    spec = _spec("memory_recall", "anthropic:claude-sonnet-4-5-20250929")
    report = _report(
        cases=[_case(input_tokens=100, output_tokens=50, cost=0.01)],
        failures=[],
        trace_id="trace-xyz",
    )
    kwargs = _usage_event_kwargs(spec=spec, report=report, duration_ms=999, org_id=ORG_ID)

    db, query = _mock_db()
    await save_usage_event(db, **kwargs)

    db.table.assert_called_once_with("usage_events")
    inserted = query.insert.call_args.args[0]
    assert inserted["org_id"] == ORG_ID
    assert inserted["agent_slug"] == "eval:memory_recall"
    assert inserted["channel"] == "eval"
    assert inserted["run_kind"] == "eval"
    assert inserted["model"] == "anthropic:claude-sonnet-4-5-20250929"
    assert inserted["input_tokens"] == 100
    assert inserted["output_tokens"] == 50
    assert inserted["cost_usd"] == 0.01
    assert inserted["duration_ms"] == 999
    assert inserted["tool_call_count"] == 0
    assert inserted["success"] is True
    assert inserted["trace_id"] == "trace-xyz"
    assert "conversation_id" not in inserted
    assert "schedule_name" not in inserted
