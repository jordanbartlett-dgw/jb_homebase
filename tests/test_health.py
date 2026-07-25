"""Health report: DB-configured agents cross-checked against live model ids.

Guards the production incident class evals can't see:
- sonnet-4 retirement (DB model invalid, health stayed green)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from anthropic import NotFoundError

from jordan_claw.health import _model_cache, build_health_report


def make_db(rows: list[dict]) -> MagicMock:
    mock_query = MagicMock()
    mock_query.execute = AsyncMock(return_value=MagicMock(data=rows))
    mock_query.eq.return_value = mock_query
    mock_query.select.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_db = MagicMock()
    mock_db.table.return_value = mock_query
    return mock_db


def make_anthropic(retrieve_side_effect=None) -> MagicMock:
    client = MagicMock()
    client.models.retrieve = AsyncMock(side_effect=retrieve_side_effect)
    return client


def not_found() -> NotFoundError:
    response = httpx.Response(404, request=httpx.Request("GET", "https://api.anthropic.com"))
    return NotFoundError("model not found", response=response, body=None)


AGENT_ROWS = [
    {
        "slug": "claw-main",
        "org_id": "org-1",
        "model": "anthropic:claude-sonnet-5",
        "is_active": True,
    },
    {
        "slug": "workout-coach",
        "org_id": "org-1",
        "model": "anthropic:claude-sonnet-5",
        "is_active": True,
    },
]


def make_db_multi(tables: dict[str, list[dict]]) -> MagicMock:
    """Mock db whose result rows depend on the table queried."""

    def table(name: str) -> MagicMock:
        mock_query = MagicMock()
        mock_query.execute = AsyncMock(return_value=MagicMock(data=tables.get(name, [])))
        mock_query.eq.return_value = mock_query
        mock_query.select.return_value = mock_query
        mock_query.limit.return_value = mock_query
        return mock_query

    mock_db = MagicMock()
    mock_db.table.side_effect = table
    return mock_db


@pytest.fixture(autouse=True)
def clear_model_cache():
    _model_cache.clear()
    yield
    _model_cache.clear()


@pytest.mark.asyncio
async def test_all_healthy():
    report = await build_health_report(
        make_db(AGENT_ROWS),
        anthropic_client=make_anthropic(),
    )
    assert report.status == "ok"
    assert report.invalid_models == []
    assert all(a.model_ok for a in report.agents)


@pytest.mark.asyncio
async def test_invalid_model_degrades():
    # The sonnet-4 retirement incident: DB model no longer served.
    report = await build_health_report(
        make_db(AGENT_ROWS),
        anthropic_client=make_anthropic(retrieve_side_effect=not_found()),
    )
    assert report.status == "degraded"
    assert report.invalid_models == ["claw-main", "workout-coach"]


@pytest.mark.asyncio
async def test_api_unavailable_does_not_degrade():
    # Transient Anthropic outage must not fail deploys: model_ok is unknown, not false.
    report = await build_health_report(
        make_db(AGENT_ROWS),
        anthropic_client=make_anthropic(retrieve_side_effect=httpx.ConnectError("boom")),
    )
    assert report.status == "ok"
    assert all(a.model_ok is None for a in report.agents)


@pytest.mark.asyncio
async def test_model_validation_is_cached():
    client = make_anthropic()
    db = make_db(AGENT_ROWS)
    await build_health_report(db, anthropic_client=client)
    await build_health_report(db, anthropic_client=client)
    # Both agents share one model string; only the first report hits the API.
    assert client.models.retrieve.await_count == 1


@pytest.mark.asyncio
async def test_non_anthropic_model_skipped():
    rows = [{"slug": "claw-main", "org_id": "org-1", "model": "openai:gpt-5", "is_active": True}]
    client = make_anthropic()
    report = await build_health_report(make_db(rows), anthropic_client=client)
    assert report.status == "ok"
    assert report.agents[0].model_ok is None
    client.models.retrieve.assert_not_awaited()


@pytest.mark.asyncio
async def test_null_model_validates_resolved_org_default():
    """Post-020 shape: agent rows are NULL and inherit organizations.default_model.
    /health must validate the RESOLVED model, not the raw NULL."""
    db = make_db_multi(
        {
            "agents": [{"slug": "claw-main", "org_id": "org-1", "model": None, "is_active": True}],
            "organizations": [{"default_model": "anthropic:claude-sonnet-5"}],
        }
    )
    client = make_anthropic()
    report = await build_health_report(db, anthropic_client=client)
    assert report.status == "ok"
    assert report.agents[0].model == "anthropic:claude-sonnet-5"
    assert report.agents[0].model_ok is True
    client.models.retrieve.assert_awaited_once_with("claude-sonnet-5")


@pytest.mark.asyncio
async def test_unresolvable_model_degrades():
    """NULL agent model + unset org default is a misconfig — gate the deploy."""
    db = make_db_multi(
        {
            "agents": [{"slug": "claw-main", "org_id": "org-1", "model": None, "is_active": True}],
            "organizations": [{"default_model": None}],
        }
    )
    report = await build_health_report(db, anthropic_client=make_anthropic())
    assert report.status == "degraded"
    assert report.invalid_models == ["claw-main"]
    assert report.agents[0].model == "(unset)"
