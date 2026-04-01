# Jordan Claw: Fastmail Calendar Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Jordan Claw the ability to read and create events on Jordan's Fastmail calendar via CalDAV.

**Architecture:** Two new Pydantic AI tools (`get_calendar_events`, `create_calendar_event`) backed by a thin `CalendarClient` wrapper around the `caldav` Python library. Sync CalDAV calls wrapped in `asyncio.to_thread()`. Fastmail auth via app-specific password.

**Tech Stack:** `caldav` library, `icalendar` (transitive dep of caldav), Pydantic AI tools, `asyncio.to_thread()`

**Spec:** `docs/superpowers/specs/2026-04-01-jordan-claw-calendar-design.md`

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `jordan-claw/pyproject.toml` | Add `caldav` dependency |
| Modify | `jordan-claw/src/jordan_claw/config.py` | Add Fastmail env vars |
| Create | `jordan-claw/src/jordan_claw/tools/calendar.py` | CalendarClient + tool functions |
| Modify | `jordan-claw/src/jordan_claw/agents/factory.py` | Register calendar tools, update system prompt |
| Create | `jordan-claw/tests/test_calendar.py` | Calendar tool tests |

---

### Task 1: Add `caldav` dependency

**Files:**
- Modify: `jordan-claw/pyproject.toml:6-16`

- [ ] **Step 1: Add caldav to dependencies**

In `jordan-claw/pyproject.toml`, add `caldav` to the dependencies list:

```toml
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "pydantic-ai-slim[anthropic]>=0.2.0",
    "pydantic-settings>=2.5.0",
    "supabase>=2.11.0",
    "aiogram>=3.13.0",
    "tavily-python>=0.5.0",
    "structlog>=24.4.0",
    "httpx>=0.27.0",
    "caldav>=1.4.0",
]
```

- [ ] **Step 2: Lock dependencies**

Run: `cd jordan-claw && uv lock`
Expected: `uv.lock` updated with `caldav` and its transitive deps.

- [ ] **Step 3: Install**

Run: `cd jordan-claw && uv sync`
Expected: `caldav` installed successfully.

- [ ] **Step 4: Commit**

```bash
cd jordan-claw
git add pyproject.toml uv.lock
git commit -m "chore: add caldav dependency for Fastmail calendar integration"
```

---

### Task 2: Add Fastmail config to Settings

**Files:**
- Modify: `jordan-claw/src/jordan_claw/config.py:7-20`

- [ ] **Step 1: Write the failing test**

Create `jordan-claw/tests/test_config.py`:

```python
from __future__ import annotations

import os

from jordan_claw.config import Settings


def test_settings_includes_fastmail_fields():
    """Settings should accept Fastmail credentials."""
    env = {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-key",
        "SUPABASE_ANON_KEY": "test-anon",
        "ANTHROPIC_API_KEY": "test-anthropic",
        "TELEGRAM_BOT_TOKEN": "test-bot",
        "TAVILY_API_KEY": "test-tavily",
        "DEFAULT_ORG_ID": "test-org",
        "FASTMAIL_USERNAME": "jordan@fastmail.com",
        "FASTMAIL_APP_PASSWORD": "app-password-123",
    }
    for k, v in env.items():
        os.environ[k] = v

    try:
        settings = Settings()
        assert settings.fastmail_username == "jordan@fastmail.com"
        assert settings.fastmail_app_password == "app-password-123"
    finally:
        for k in env:
            os.environ.pop(k, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jordan-claw && uv run pytest tests/test_config.py::test_settings_includes_fastmail_fields -v`
Expected: FAIL — `Settings` has no `fastmail_username` field.

- [ ] **Step 3: Add Fastmail fields to Settings**

In `jordan-claw/src/jordan_claw/config.py`, add two fields to the `Settings` class after `tavily_api_key`:

```python
class Settings(BaseSettings):
    supabase_url: str
    supabase_service_key: str
    supabase_anon_key: str
    anthropic_api_key: str
    telegram_bot_token: str
    tavily_api_key: str
    fastmail_username: str
    fastmail_app_password: str
    default_org_id: str
    default_agent_slug: str = "claw-main"
    log_level: str = "INFO"
    environment: str = "development"
    message_history_limit: int = 50

    model_config = ConfigDict(env_file=".env")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd jordan-claw && uv run pytest tests/test_config.py::test_settings_includes_fastmail_fields -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd jordan-claw
git add src/jordan_claw/config.py tests/test_config.py
git commit -m "feat: add Fastmail credentials to Settings"
```

---

### Task 3: Build CalendarClient and tool functions

**Files:**
- Create: `jordan-claw/src/jordan_claw/tools/calendar.py`
- Create: `jordan-claw/tests/test_calendar.py`

- [ ] **Step 1: Write the failing test for get_calendar_events (events found)**

Create `jordan-claw/tests/test_calendar.py`:

```python
from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from jordan_claw.tools.calendar import get_calendar_events


def _make_mock_event(summary: str, dtstart: datetime, dtend: datetime, location: str | None = None):
    """Create a mock caldav event with icalendar-like vEvent access."""
    vevent = MagicMock()
    vevent["SUMMARY"].to_ical.return_value = summary.encode()
    vevent["DTSTART"].dt = dtstart
    vevent["DTEND"].dt = dtend
    if location:
        vevent.__contains__ = lambda self, key: key == "LOCATION"
        vevent.__getitem__ = lambda self, key: MagicMock(
            to_ical=MagicMock(return_value=location.encode())
        ) if key == "LOCATION" else {
            "SUMMARY": vevent["SUMMARY"],
            "DTSTART": vevent["DTSTART"],
            "DTEND": vevent["DTEND"],
        }[key]
    else:
        vevent.__contains__ = lambda self, key: False

    event = MagicMock()
    event.vobject_instance.vevent = MagicMock()

    ical_event = MagicMock()
    ical_event.walk.return_value = [vevent]
    event.icalendar_instance = ical_event

    return event


@pytest.mark.asyncio
async def test_get_events_returns_formatted_list():
    tz = ZoneInfo("America/Chicago")
    events = [
        _make_mock_event(
            "Team standup",
            datetime(2026, 4, 2, 9, 0, tzinfo=tz),
            datetime(2026, 4, 2, 9, 30, tzinfo=tz),
        ),
        _make_mock_event(
            "Lunch with Sarah",
            datetime(2026, 4, 2, 12, 0, tzinfo=tz),
            datetime(2026, 4, 2, 13, 0, tzinfo=tz),
        ),
    ]

    mock_calendar = MagicMock()
    mock_calendar.search.return_value = events

    with patch("jordan_claw.tools.calendar._get_calendar", return_value=mock_calendar):
        result = await get_calendar_events("2026-04-02", "2026-04-02")

    assert "Team standup" in result
    assert "Lunch with Sarah" in result
    assert "09:00" in result
    assert "12:00" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jordan-claw && uv run pytest tests/test_calendar.py::test_get_events_returns_formatted_list -v`
Expected: FAIL — `jordan_claw.tools.calendar` does not exist.

- [ ] **Step 3: Write minimal calendar module**

Create `jordan-claw/src/jordan_claw/tools/calendar.py`:

```python
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import caldav
import structlog

logger = structlog.get_logger()

CENTRAL_TZ = ZoneInfo("America/Chicago")

# Module-level cached calendar reference
_calendar: caldav.Calendar | None = None
_caldav_url: str | None = None
_caldav_username: str | None = None
_caldav_password: str | None = None


def configure_calendar(username: str, app_password: str) -> None:
    """Store CalDAV credentials for lazy connection."""
    global _caldav_url, _caldav_username, _caldav_password, _calendar
    _caldav_url = f"https://caldav.fastmail.com/dav/calendars/user/{username}/"
    _caldav_username = username
    _caldav_password = app_password
    _calendar = None  # Reset cache on reconfigure


def _get_calendar() -> caldav.Calendar:
    """Get or create the cached calendar connection."""
    global _calendar
    if _calendar is not None:
        return _calendar

    if not _caldav_url or not _caldav_username or not _caldav_password:
        raise RuntimeError("Calendar not configured. Call configure_calendar() first.")

    client = caldav.DAVClient(
        url=_caldav_url,
        username=_caldav_username,
        password=_caldav_password,
    )
    principal = client.principal()
    calendars = principal.calendars()
    if not calendars:
        raise RuntimeError("No calendars found on Fastmail account.")

    _calendar = calendars[0]
    return _calendar


async def get_calendar_events(start_date: str, end_date: str) -> str:
    """Fetch calendar events for a date range.

    Args:
        start_date: ISO date string (YYYY-MM-DD)
        end_date: ISO date string (YYYY-MM-DD)
    """
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=CENTRAL_TZ)
        end = datetime.strptime(end_date, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=CENTRAL_TZ
        )
    except ValueError:
        return "Invalid date format. Use YYYY-MM-DD."

    try:
        calendar = await asyncio.to_thread(_get_calendar)
        results = await asyncio.to_thread(
            calendar.search,
            start=start,
            end=end,
            event=True,
            expand=True,
        )
    except Exception as e:
        logger.error("caldav_search_failed", error=str(e))
        return f"Could not reach calendar: {e}"

    if not results:
        return "No events scheduled."

    events = []
    for item in results:
        try:
            cal = item.icalendar_instance
            for component in cal.walk():
                if component.name != "VEVENT":
                    continue
                summary = component["SUMMARY"].to_ical().decode()
                dtstart = component["DTSTART"].dt
                dtend = component["DTEND"].dt

                if hasattr(dtstart, "strftime"):
                    start_str = dtstart.astimezone(CENTRAL_TZ).strftime("%H:%M")
                    end_str = dtend.astimezone(CENTRAL_TZ).strftime("%H:%M")
                else:
                    start_str = str(dtstart)
                    end_str = str(dtend)

                line = f"- {summary}: {start_str} - {end_str}"

                if "LOCATION" in component:
                    location = component["LOCATION"].to_ical().decode()
                    line += f" ({location})"

                events.append((dtstart, line))
        except Exception as e:
            logger.warning("caldav_event_parse_error", error=str(e))
            continue

    if not events:
        return "No events scheduled."

    events.sort(key=lambda x: x[0])
    return "\n".join(line for _, line in events)


async def create_calendar_event(
    title: str,
    start: str,
    end: str,
    location: str | None = None,
    description: str | None = None,
) -> str:
    """Create a calendar event.

    Args:
        title: Event title
        start: ISO datetime string (YYYY-MM-DDTHH:MM:SS)
        end: ISO datetime string (YYYY-MM-DDTHH:MM:SS)
        location: Optional location
        description: Optional description
    """
    try:
        dtstart = datetime.fromisoformat(start).replace(tzinfo=CENTRAL_TZ)
        dtend = datetime.fromisoformat(end).replace(tzinfo=CENTRAL_TZ)
    except ValueError:
        return "Invalid datetime format. Use YYYY-MM-DDTHH:MM:SS."

    vcal = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//Jordan Claw//EN\r\n"
        "BEGIN:VEVENT\r\n"
        f"SUMMARY:{title}\r\n"
        f"DTSTART:{dtstart.strftime('%Y%m%dT%H%M%S')}\r\n"
        f"DTEND:{dtend.strftime('%Y%m%dT%H%M%S')}\r\n"
    )
    if location:
        vcal += f"LOCATION:{location}\r\n"
    if description:
        vcal += f"DESCRIPTION:{description}\r\n"
    vcal += "END:VEVENT\r\nEND:VCALENDAR\r\n"

    try:
        calendar = await asyncio.to_thread(_get_calendar)
        await asyncio.to_thread(calendar.save_event, vcal)
    except Exception as e:
        logger.error("caldav_create_failed", error=str(e))
        return f"Could not create event: {e}"

    date_str = dtstart.strftime("%B %d, %Y")
    start_str = dtstart.strftime("%I:%M %p").lstrip("0")
    end_str = dtend.strftime("%I:%M %p").lstrip("0")

    return f"Created: {title} on {date_str} from {start_str} to {end_str}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd jordan-claw && uv run pytest tests/test_calendar.py::test_get_events_returns_formatted_list -v`
Expected: PASS

- [ ] **Step 5: Write test for empty calendar**

Add to `jordan-claw/tests/test_calendar.py`:

```python
@pytest.mark.asyncio
async def test_get_events_empty_calendar():
    mock_calendar = MagicMock()
    mock_calendar.search.return_value = []

    with patch("jordan_claw.tools.calendar._get_calendar", return_value=mock_calendar):
        result = await get_calendar_events("2026-04-02", "2026-04-02")

    assert result == "No events scheduled."
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd jordan-claw && uv run pytest tests/test_calendar.py::test_get_events_empty_calendar -v`
Expected: PASS (implementation already handles empty list)

- [ ] **Step 7: Write test for create_calendar_event**

Add import at top of test file:

```python
from jordan_claw.tools.calendar import create_calendar_event
```

Add test:

```python
@pytest.mark.asyncio
async def test_create_event_success():
    mock_calendar = MagicMock()
    mock_calendar.save_event = MagicMock()

    with patch("jordan_claw.tools.calendar._get_calendar", return_value=mock_calendar):
        result = await create_calendar_event(
            title="Meeting with Sarah",
            start="2026-04-02T14:00:00",
            end="2026-04-02T14:30:00",
        )

    assert "Created: Meeting with Sarah" in result
    assert "April 02, 2026" in result
    assert "2:00 PM" in result
    assert "2:30 PM" in result

    # Verify iCal data was passed
    call_args = mock_calendar.save_event.call_args[0][0]
    assert "SUMMARY:Meeting with Sarah" in call_args
    assert "DTSTART:" in call_args
    assert "DTEND:" in call_args
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd jordan-claw && uv run pytest tests/test_calendar.py::test_create_event_success -v`
Expected: PASS

- [ ] **Step 9: Write test for create with optional fields**

```python
@pytest.mark.asyncio
async def test_create_event_with_optional_fields():
    mock_calendar = MagicMock()
    mock_calendar.save_event = MagicMock()

    with patch("jordan_claw.tools.calendar._get_calendar", return_value=mock_calendar):
        result = await create_calendar_event(
            title="Coffee",
            start="2026-04-02T10:00:00",
            end="2026-04-02T10:30:00",
            location="Blue Bottle Coffee",
            description="Catch up on project status",
        )

    assert "Created: Coffee" in result

    call_args = mock_calendar.save_event.call_args[0][0]
    assert "LOCATION:Blue Bottle Coffee" in call_args
    assert "DESCRIPTION:Catch up on project status" in call_args
```

- [ ] **Step 10: Run test to verify it passes**

Run: `cd jordan-claw && uv run pytest tests/test_calendar.py::test_create_event_with_optional_fields -v`
Expected: PASS

- [ ] **Step 11: Write test for CalDAV connection error**

```python
@pytest.mark.asyncio
async def test_caldav_connection_error():
    with patch(
        "jordan_claw.tools.calendar._get_calendar",
        side_effect=Exception("Connection refused"),
    ):
        result = await get_calendar_events("2026-04-02", "2026-04-02")

    assert "Could not reach calendar" in result
```

- [ ] **Step 12: Run test to verify it passes**

Run: `cd jordan-claw && uv run pytest tests/test_calendar.py::test_caldav_connection_error -v`
Expected: PASS

- [ ] **Step 13: Run all calendar tests**

Run: `cd jordan-claw && uv run pytest tests/test_calendar.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 14: Commit**

```bash
cd jordan-claw
git add src/jordan_claw/tools/calendar.py tests/test_calendar.py
git commit -m "feat: add CalDAV calendar client with get and create tools"
```

---

### Task 4: Register calendar tools in the agent

**Files:**
- Modify: `jordan-claw/src/jordan_claw/agents/factory.py:1-56`

- [ ] **Step 1: Update system prompt and register tools**

In `jordan-claw/src/jordan_claw/agents/factory.py`, add the calendar import and update the system prompt and `create_agent` function:

Add import at top:

```python
from jordan_claw.tools.calendar import (
    configure_calendar,
    create_calendar_event,
    get_calendar_events,
)
```

Add to the end of `SYSTEM_PROMPT` (before the closing `\"`):

```python
You also have access to Jordan's calendar. You can check what's scheduled and \
create new events. Always call current_datetime first to resolve relative dates \
like "tomorrow" or "next Friday" before calling calendar tools. When creating \
events where the user gives a duration instead of an end time, calculate the \
end time yourself.\
```

Update `create_agent` signature and add calendar tools:

```python
def create_agent(
    *,
    tavily_api_key: str,
    fastmail_username: str,
    fastmail_app_password: str,
) -> Agent:
    """Create the Phase 1 hardcoded Pydantic AI agent."""
    configure_calendar(fastmail_username, fastmail_app_password)

    agent = Agent(
        "anthropic:claude-sonnet-4-20250514",
        system_prompt=SYSTEM_PROMPT,
    )

    @agent.tool_plain
    def current_datetime() -> str:
        """Get the current date and time in US Central time."""
        return get_current_datetime()

    @agent.tool_plain
    async def search_web(query: str) -> str:
        """Search the web for current information.

        Use for questions about recent events, facts, or anything
        that benefits from up-to-date data.
        """
        return await web_search(query, api_key=tavily_api_key)

    @agent.tool_plain
    async def check_calendar(start_date: str, end_date: str) -> str:
        """Check Jordan's calendar for events in a date range.

        Args:
            start_date: Start date as YYYY-MM-DD
            end_date: End date as YYYY-MM-DD
        """
        return await get_calendar_events(start_date, end_date)

    @agent.tool_plain
    async def schedule_event(
        title: str,
        start: str,
        end: str,
        location: str | None = None,
        description: str | None = None,
    ) -> str:
        """Create a new event on Jordan's calendar.

        Args:
            title: Event title
            start: Start datetime as YYYY-MM-DDTHH:MM:SS
            end: End datetime as YYYY-MM-DDTHH:MM:SS
            location: Optional location
            description: Optional description
        """
        return await create_calendar_event(title, start, end, location, description)

    return agent
```

- [ ] **Step 2: Update all call sites of create_agent**

Find where `create_agent` is called and add the new kwargs. In `jordan-claw/src/jordan_claw/gateway/router.py`, find the `create_agent(...)` call and add:

```python
agent = create_agent(
    tavily_api_key=tavily_api_key,
    fastmail_username=settings.fastmail_username,
    fastmail_app_password=settings.fastmail_app_password,
)
```

If `settings` is not already available in `router.py`, import and call `get_settings()`:

```python
from jordan_claw.config import get_settings
```

And add `settings = get_settings()` at the point of use.

- [ ] **Step 3: Run existing tests to check for breakage**

Run: `cd jordan-claw && uv run pytest tests/ -v`
Expected: Some tests may fail because `create_agent` now requires `fastmail_username` and `fastmail_app_password`. Fix test mocks in `test_gateway.py` if needed — the `create_agent` mock in `test_gateway.py` uses `patch` so it should still work since it replaces the function entirely. Verify.

- [ ] **Step 4: Fix any broken tests**

If `test_gateway.py` tests break because `create_agent` is patched but called with new kwargs, the existing `patch("jordan_claw.gateway.router.create_agent")` mock should absorb extra kwargs. Verify all tests pass.

Run: `cd jordan-claw && uv run pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
cd jordan-claw
git add src/jordan_claw/agents/factory.py src/jordan_claw/gateway/router.py
git commit -m "feat: register calendar tools in agent and update system prompt"
```

---

### Task 5: Update .env.example and verify end-to-end

**Files:**
- Modify: `jordan-claw/.env.example`

- [ ] **Step 1: Update .env.example**

Add to `jordan-claw/.env.example`:

```
FASTMAIL_USERNAME=your-email@fastmail.com
FASTMAIL_APP_PASSWORD=your-app-specific-password
```

- [ ] **Step 2: Run full test suite**

Run: `cd jordan-claw && uv run pytest tests/ -v`
Expected: All tests PASS (existing + new calendar tests).

- [ ] **Step 3: Run ruff**

Run: `cd jordan-claw && uv run ruff check src/ tests/`
Expected: No errors.

Run: `cd jordan-claw && uv run ruff format --check src/ tests/`
Expected: No formatting issues.

- [ ] **Step 4: Commit**

```bash
cd jordan-claw
git add .env.example
git commit -m "chore: add Fastmail env vars to .env.example"
```
