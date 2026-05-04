from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

CHICAGO = ZoneInfo("America/Chicago")


def _wrapper_returning(output: str) -> AsyncMock:
    return AsyncMock(return_value=SimpleNamespace(output=output))


def _mock_settings() -> MagicMock:
    s = MagicMock()
    s.fastmail_username = "user@test.com"
    s.fastmail_app_password = "test-pass"
    s.openai_api_key = "test-openai"
    s.default_org_id = "org-1"
    s.default_agent_slug = "claw-main"
    s.tavily_api_key = "test-tavily"
    return s


@pytest.mark.asyncio
async def test_morning_briefing_returns_message():
    from jordan_claw.proactive.executors import execute_morning_briefing

    mock_db = AsyncMock()

    with (
        patch(
            "jordan_claw.proactive.executors.get_calendar_events",
            new=AsyncMock(return_value="- Team standup: 09:00 - 09:30"),
        ),
        patch(
            "jordan_claw.proactive.executors.load_memory_context",
            new=AsyncMock(return_value="## Memory\n- Jordan likes coffee"),
        ),
        patch(
            "jordan_claw.proactive.executors.build_agent",
            new=AsyncMock(return_value=(MagicMock(), "anthropic:claude-haiku-4-5-20251001")),
        ),
        patch(
            "jordan_claw.proactive.executors.run_agent_instrumented",
            new=_wrapper_returning("Good morning! Here's your briefing."),
        ),
    ):
        result = await execute_morning_briefing(
            mock_db, "org-1", {"agent_slug": "claw-main"}, _mock_settings()
        )

    assert result == "Good morning! Here's your briefing."


@pytest.mark.asyncio
async def test_weekly_review_returns_message():
    from jordan_claw.proactive.executors import execute_weekly_review

    mock_db = AsyncMock()

    with (
        patch(
            "jordan_claw.proactive.executors.get_calendar_events",
            new=AsyncMock(return_value="- Monday standup: 09:00"),
        ),
        patch(
            "jordan_claw.proactive.executors.load_memory_context",
            new=AsyncMock(return_value=""),
        ),
        patch(
            "jordan_claw.proactive.executors.get_recent_events",
            new=AsyncMock(
                return_value=[
                    {
                        "summary": "Decided on new logo",
                        "created_at": "2026-04-03T10:00:00",
                    }
                ]
            ),
        ),
        patch(
            "jordan_claw.proactive.executors.build_agent",
            new=AsyncMock(return_value=(MagicMock(), "anthropic:claude-haiku-4-5-20251001")),
        ),
        patch(
            "jordan_claw.proactive.executors.run_agent_instrumented",
            new=_wrapper_returning("This week you had 12 meetings."),
        ),
    ):
        result = await execute_weekly_review(
            mock_db, "org-1", {"agent_slug": "claw-main"}, _mock_settings()
        )

    assert result == "This week you had 12 meetings."


@pytest.mark.asyncio
async def test_daily_scan_no_conflicts_returns_empty():
    from jordan_claw.proactive.executors import execute_daily_scan

    with patch(
        "jordan_claw.proactive.executors.get_calendar_events",
        new=AsyncMock(return_value="- Standup: 09:00 - 09:30\n- Lunch: 12:00 - 13:00"),
    ):
        result = await execute_daily_scan(
            AsyncMock(), "org-1", {}, _mock_settings()
        )

    assert result == ""


@pytest.mark.asyncio
async def test_daily_scan_detects_conflicts():
    from jordan_claw.proactive.executors import execute_daily_scan

    # Two events that overlap: 09:00-10:00 and 09:30-10:30
    events_text = "- Meeting A: 09:00 - 10:00\n- Meeting B: 09:30 - 10:30"

    with (
        patch(
            "jordan_claw.proactive.executors.get_calendar_events",
            new=AsyncMock(return_value=events_text),
        ),
        patch(
            "jordan_claw.proactive.executors._parse_event_times",
            return_value=[
                (
                    "Meeting A",
                    datetime(2026, 4, 5, 9, 0, tzinfo=CHICAGO),
                    datetime(2026, 4, 5, 10, 0, tzinfo=CHICAGO),
                ),
                (
                    "Meeting B",
                    datetime(2026, 4, 5, 9, 30, tzinfo=CHICAGO),
                    datetime(2026, 4, 5, 10, 30, tzinfo=CHICAGO),
                ),
            ],
        ),
    ):
        result = await execute_daily_scan(
            AsyncMock(), "org-1", {}, _mock_settings()
        )

    assert "conflict" in result.lower() or "overlap" in result.lower()


@pytest.mark.asyncio
async def test_calendar_reminder_returns_brief():
    from jordan_claw.proactive.executors import execute_calendar_reminder

    mock_db = AsyncMock()
    brief = "Meeting with Sarah in 30 min. She's the DGW marketing lead."

    with (
        patch(
            "jordan_claw.proactive.executors.load_memory_context",
            new=AsyncMock(return_value="## Memory\n- Sarah: DGW marketing lead"),
        ),
        patch(
            "jordan_claw.proactive.executors.build_agent",
            new=AsyncMock(return_value=(MagicMock(), "anthropic:claude-haiku-4-5-20251001")),
        ),
        patch(
            "jordan_claw.proactive.executors.run_agent_instrumented",
            new=_wrapper_returning(brief),
        ),
    ):
        result = await execute_calendar_reminder(
            mock_db,
            "org-1",
            {"agent_slug": "claw-main"},
            _mock_settings(),
            event_title="Sync with Sarah",
            event_time="09:30",
        )

    assert len(result) > 0


def test_format_memory_flag():
    from jordan_claw.proactive.executors import format_memory_flag

    result = format_memory_flag(
        old_content="Jordan prefers tea",
        new_content="Jordan prefers coffee",
    )
    assert "tea" in result
    assert "coffee" in result
