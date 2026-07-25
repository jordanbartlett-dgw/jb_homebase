from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import httpx

from jordan_claw.gateway.app_today import DailyDigest, TodayResponse, load_today
from jordan_claw.tools.calendar import CalendarAccessError, CalendarEvent

CHICAGO = ZoneInfo("America/Chicago")
NOW = datetime(2026, 7, 25, 8, 30, tzinfo=CHICAGO)
EVENT = CalendarEvent(
    id="event-1",
    title="Board call",
    starts_at=datetime(2026, 7, 25, 10, 0, tzinfo=CHICAGO),
    ends_at=datetime(2026, 7, 25, 11, 0, tzinfo=CHICAGO),
    all_day=False,
    location="Zoom",
)


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
    settings.fastmail_username = "jordan@example.com"
    settings.fastmail_app_password = "password"
    app.state.settings = settings
    app.state.db = MagicMock()


async def test_load_today_returns_existing_digest_and_calendar_without_agent_run():
    digest_row = {
        "id": "digest-1",
        "content": "You have one board call today.",
        "delivered_at": "2026-07-25T07:02:00-05:00",
    }
    with (
        patch(
            "jordan_claw.gateway.app_today.get_latest_proactive_message",
            new=AsyncMock(return_value=digest_row),
        ) as digest_query,
        patch(
            "jordan_claw.gateway.app_today.list_calendar_events",
            new=AsyncMock(return_value=[EVENT]),
        ) as calendar_query,
    ):
        response = await load_today(
            MagicMock(),
            org_id="org-1",
            fastmail_username="jordan@example.com",
            fastmail_app_password="password",
            days=7,
            now=NOW,
        )

    assert response.digest is not None
    assert response.digest.content == "You have one board call today."
    assert response.events == [EVENT]
    assert response.calendar_status == "ok"
    assert digest_query.await_args.kwargs["task_type"] == "morning_briefing"
    assert calendar_query.await_args.args[2].date().isoformat() == "2026-07-25"
    assert calendar_query.await_args.args[3].date().isoformat() == "2026-08-01"


async def test_load_today_keeps_digest_when_calendar_is_unavailable():
    digest_row = {
        "id": "digest-1",
        "content": "Your briefing is ready.",
        "delivered_at": "2026-07-25T07:02:00-05:00",
    }
    with (
        patch(
            "jordan_claw.gateway.app_today.get_latest_proactive_message",
            new=AsyncMock(return_value=digest_row),
        ),
        patch(
            "jordan_claw.gateway.app_today.list_calendar_events",
            new=AsyncMock(side_effect=CalendarAccessError("offline")),
        ),
    ):
        response = await load_today(
            MagicMock(),
            org_id="org-1",
            fastmail_username="jordan@example.com",
            fastmail_app_password="password",
            days=7,
            now=NOW,
        )

    assert response.digest is not None
    assert response.calendar_status == "unavailable"
    assert response.calendar_message == "Calendar is temporarily unavailable."
    assert response.events == []


async def test_today_route_requires_app_auth():
    _wire_app_state()
    async with _client() as client:
        response = await client.get(
            "/app/today",
            headers={"Authorization": "Bearer wrong"},
        )

    assert response.status_code == 401


async def test_today_route_returns_structured_payload():
    from jordan_claw import main

    _wire_app_state()
    payload = TodayResponse(
        date="2026-07-25",
        timezone="America/Chicago",
        digest=DailyDigest(
            id="digest-1",
            content="Your briefing is ready.",
            generated_at=datetime(2026, 7, 25, 7, 2, tzinfo=CHICAGO),
        ),
        calendar_status="ok",
        events=[EVENT],
    )

    with patch.object(main, "load_today", new=AsyncMock(return_value=payload)) as loader:
        async with _client() as client:
            response = await client.get(
                "/app/today",
                params={"days": 7},
                headers={"Authorization": "Bearer app-token"},
            )

    assert response.status_code == 200
    assert response.json()["digest"]["content"] == "Your briefing is ready."
    assert response.json()["events"][0]["title"] == "Board call"
    assert loader.await_args.kwargs["org_id"] == "org-1"
    assert loader.await_args.kwargs["days"] == 7
