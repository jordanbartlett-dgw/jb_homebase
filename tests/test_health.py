"""Health report: DB-configured agents cross-checked against running bots and live model ids.

Guards the two prod incident classes evals can't see:
- sonnet-4 retirement (DB model invalid, health stayed green)
- 2026-07-05 missing WORKOUT_TELEGRAM_BOT_TOKEN (active agent, no dispatcher)
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
    {"slug": "claw-main", "model": "anthropic:claude-sonnet-5", "is_active": True},
    {"slug": "workout-coach", "model": "anthropic:claude-sonnet-5", "is_active": True},
]


@pytest.fixture(autouse=True)
def clear_model_cache():
    _model_cache.clear()
    yield
    _model_cache.clear()


@pytest.mark.asyncio
async def test_all_healthy():
    report = await build_health_report(
        make_db(AGENT_ROWS),
        running_bots={"claw-main", "workout-coach"},
        anthropic_client=make_anthropic(),
    )
    assert report.status == "ok"
    assert report.missing_bots == []
    assert report.invalid_models == []
    assert all(a.bot_running and a.model_ok for a in report.agents)


@pytest.mark.asyncio
async def test_active_agent_without_bot_degrades():
    # The 2026-07-05 incident: workout-coach active in DB, dispatcher never started.
    report = await build_health_report(
        make_db(AGENT_ROWS),
        running_bots={"claw-main"},
        anthropic_client=make_anthropic(),
    )
    assert report.status == "degraded"
    assert report.missing_bots == ["workout-coach"]


@pytest.mark.asyncio
async def test_invalid_model_degrades():
    # The sonnet-4 retirement incident: DB model no longer served.
    report = await build_health_report(
        make_db(AGENT_ROWS),
        running_bots={"claw-main", "workout-coach"},
        anthropic_client=make_anthropic(retrieve_side_effect=not_found()),
    )
    assert report.status == "degraded"
    assert report.invalid_models == ["claw-main", "workout-coach"]


@pytest.mark.asyncio
async def test_api_unavailable_does_not_degrade():
    # Transient Anthropic outage must not fail deploys: model_ok is unknown, not false.
    report = await build_health_report(
        make_db(AGENT_ROWS),
        running_bots={"claw-main", "workout-coach"},
        anthropic_client=make_anthropic(retrieve_side_effect=httpx.ConnectError("boom")),
    )
    assert report.status == "ok"
    assert all(a.model_ok is None for a in report.agents)


@pytest.mark.asyncio
async def test_model_validation_is_cached():
    client = make_anthropic()
    db = make_db(AGENT_ROWS)
    await build_health_report(db, running_bots=set(), anthropic_client=client)
    await build_health_report(db, running_bots=set(), anthropic_client=client)
    # Both agents share one model string; only the first report hits the API.
    assert client.models.retrieve.await_count == 1


@pytest.mark.asyncio
async def test_non_anthropic_model_skipped():
    rows = [{"slug": "claw-main", "model": "openai:gpt-5", "is_active": True}]
    client = make_anthropic()
    report = await build_health_report(
        make_db(rows), running_bots={"claw-main"}, anthropic_client=client
    )
    assert report.status == "ok"
    assert report.agents[0].model_ok is None
    client.models.retrieve.assert_not_awaited()
