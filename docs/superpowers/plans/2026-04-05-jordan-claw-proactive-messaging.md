# Proactive Messaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add proactive messaging to Jordan Claw so the agent initiates contact via Telegram on schedules, calendar reminders, and memory corrections.

**Architecture:** In-process async scheduler loop checks DB-driven cron schedules every 60 seconds. Task executors compose messages via the existing Pydantic AI agent. Event-triggered nudges (calendar reminders, memory flags) fire from existing code paths. All messages route through a single delivery function that sends via Telegram and logs to an audit table.

**Tech Stack:** Python 3.12, FastAPI, Pydantic AI, aiogram, Supabase, croniter, asyncio

---

### Task 1: Calendar Globals Refactor

Remove module-level credential globals from `tools/calendar.py`. Pass credentials as function parameters instead.

**Files:**
- Modify: `src/jordan_claw/tools/calendar.py`
- Modify: `tests/test_calendar.py`

- [ ] **Step 1: Update `test_calendar.py` — remove `reset_calendar_module` fixture and rewrite tests to pass credentials**

Replace the `reset_calendar_module` fixture and rewrite all tests so they pass `username` and `app_password` to `get_calendar_events()` and `create_calendar_event()`. Remove tests for `configure_calendar` and cache reset (those features are being deleted).

In `tests/test_calendar.py`, make these changes:

1. Delete the `reset_calendar_module` fixture entirely (lines 13-20)
2. Delete `test_tool_without_configure_returns_error` (lines 253-264) — no longer applicable
3. Delete `test_configure_calendar_resets_cache` (lines 267-282) — feature being removed

4. Update `test_get_events_returns_formatted_list`: patch `_connect_calendar` instead of `_get_calendar_async`:

```python
@pytest.mark.asyncio
async def test_get_events_returns_formatted_list():
    from jordan_claw.tools.calendar import get_calendar_events

    start = datetime(2026, 4, 1, 9, 0, tzinfo=CHICAGO)
    end = datetime(2026, 4, 1, 10, 0, tzinfo=CHICAGO)
    start2 = datetime(2026, 4, 1, 14, 0, tzinfo=CHICAGO)
    end2 = datetime(2026, 4, 1, 15, 30, tzinfo=CHICAGO)

    items = [
        _make_calendar_item([_make_vevent("Team standup", start, end)]),
        _make_calendar_item([_make_vevent("Client call", start2, end2)]),
    ]
    mock_cal = _make_mock_calendar(items)

    with patch(
        "jordan_claw.tools.calendar._connect_calendar",
        return_value=mock_cal,
    ):
        result = await get_calendar_events(
            "user@test.com", "test-pass",
            datetime(2026, 4, 1, tzinfo=CHICAGO),
            datetime(2026, 4, 2, tzinfo=CHICAGO),
        )

    assert "Team standup" in result
    assert "09:00" in result
    assert "Client call" in result
```

5. Apply the same pattern to all other test functions: patch `_connect_calendar` (sync, returns mock calendar), pass `"user@test.com", "test-pass"` as the first two args to `get_calendar_events` or `create_calendar_event`.

6. Update `test_caldav_connection_error` to make `_connect_calendar` raise instead:

```python
@pytest.mark.asyncio
async def test_caldav_connection_error():
    from jordan_claw.tools.calendar import get_calendar_events

    with patch(
        "jordan_claw.tools.calendar._connect_calendar",
        side_effect=Exception("Connection refused"),
    ):
        result = await get_calendar_events(
            "user@test.com", "test-pass",
            datetime(2026, 4, 1, tzinfo=CHICAGO),
            datetime(2026, 4, 2, tzinfo=CHICAGO),
        )

    assert "error" in result.lower() or "Error" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jordan-claw && uv run pytest tests/test_calendar.py -v`
Expected: FAIL — `get_calendar_events` and `create_calendar_event` don't accept username/app_password params yet.

- [ ] **Step 3: Refactor `tools/calendar.py` — remove globals, pass credentials through**

In `src/jordan_claw/tools/calendar.py`:

1. Delete these module-level globals (lines 19-23):
```python
_username: str | None = None
_app_password: str | None = None
_calendar_cache: caldav.Calendar | None = None
_cache_lock: asyncio.Lock | None = None
```

2. Delete `_get_lock()` (lines 26-30)
3. Delete `configure_calendar()` (lines 33-40)
4. Delete `_reset()` (lines 43-49)
5. Delete `_get_calendar_async()` (lines 72-87)

6. Rewrite `_connect_calendar` to accept credentials:

```python
def _connect_calendar(username: str, app_password: str) -> caldav.Calendar:
    """Connect to Fastmail CalDAV and return the default calendar.

    Called via asyncio.to_thread() from async code.
    """
    url = f"https://caldav.fastmail.com/dav/calendars/user/{username}/"
    client = caldav.DAVClient(url=url, username=username, password=app_password)
    principal = client.principal()
    calendars = principal.calendars()

    if not calendars:
        raise RuntimeError("No calendars found on Fastmail account.")

    return calendars[0]
```

7. Update `get_calendar_events` signature and body:

```python
async def get_calendar_events(
    username: str, app_password: str,
    start_date: str | datetime, end_date: str | datetime,
) -> str:
    """Query CalDAV for events in a date range and return formatted text."""
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, "%Y-%m-%d")
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)

    if start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=CENTRAL_TZ)
    if end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=CENTRAL_TZ)

    try:
        calendar = await asyncio.to_thread(_connect_calendar, username, app_password)
        items = await asyncio.to_thread(calendar.search, start=start_date, end=end_date, event=True)
    except Exception as exc:
        log.error("calendar.get_events.failed", error=str(exc))
        return f"Error fetching calendar events: {exc}"

    lines: list[str] = []
    for item in items:
        try:
            for comp in item.icalendar_instance.walk():
                if comp.name != "VEVENT":
                    continue
                summary = comp["SUMMARY"].to_ical().decode()
                start = comp["DTSTART"].dt
                end = comp["DTEND"].dt
                line = f"- {summary}: {_format_dt(start)} - {_format_dt(end)}"
                if "LOCATION" in comp:
                    location = comp["LOCATION"].to_ical().decode()
                    line += f" ({location})"
                lines.append(line)
        except Exception as exc:
            log.warning("calendar.parse_event.failed", error=str(exc))
            continue

    if not lines:
        return "No events scheduled."

    return "\n".join(lines)
```

8. Update `create_calendar_event` signature:

```python
async def create_calendar_event(
    username: str, app_password: str,
    title: str,
    start: str | datetime,
    end: str | datetime,
    location: str | None = None,
    description: str | None = None,
) -> str:
```

And replace the internal `await _get_calendar_async()` call with:
```python
        calendar = await asyncio.to_thread(_connect_calendar, username, app_password)
```

9. Update the tool functions to pass credentials through:

```python
async def check_calendar(ctx: RunContext[AgentDeps], start_date: str, end_date: str) -> str:
    """Check Jordan's calendar for events in a date range.

    Args:
        start_date: Start date as YYYY-MM-DD
        end_date: End date as YYYY-MM-DD
    """
    return await get_calendar_events(
        ctx.deps.fastmail_username, ctx.deps.fastmail_app_password,
        start_date, end_date,
    )


async def schedule_event(
    ctx: RunContext[AgentDeps],
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
    return await create_calendar_event(
        ctx.deps.fastmail_username, ctx.deps.fastmail_app_password,
        title, start, end, location, description,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd jordan-claw && uv run pytest tests/test_calendar.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Run ruff**

Run: `cd jordan-claw && uv run ruff check src/jordan_claw/tools/calendar.py tests/test_calendar.py --fix`
Expected: Clean or auto-fixed.

- [ ] **Step 6: Commit**

```bash
cd jordan-claw && git add src/jordan_claw/tools/calendar.py tests/test_calendar.py
git commit -m "refactor: remove calendar module globals, pass credentials as parameters"
```

---

### Task 2: Database Migration

Create the migration SQL for the two new tables and the orgs table change.

**Files:**
- Create: `jordan-claw/migrations/004_proactive_tables.sql`

- [ ] **Step 1: Write the migration SQL**

Create `jordan-claw/migrations/004_proactive_tables.sql`:

```sql
-- Proactive Messaging tables (Phase 3c)

-- Add telegram_chat_id to orgs for outbound message delivery
ALTER TABLE orgs ADD COLUMN IF NOT EXISTS telegram_chat_id bigint;

-- Scheduled proactive task definitions
CREATE TABLE IF NOT EXISTS proactive_schedules (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id uuid NOT NULL REFERENCES orgs(id),
    name text NOT NULL,
    cron_expression text NOT NULL,
    timezone text NOT NULL DEFAULT 'America/Chicago',
    enabled boolean NOT NULL DEFAULT true,
    task_type text NOT NULL,
    config jsonb NOT NULL DEFAULT '{}',
    last_run_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Audit log of proactive messages sent
CREATE TABLE IF NOT EXISTS proactive_messages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id uuid NOT NULL REFERENCES orgs(id),
    schedule_id uuid REFERENCES proactive_schedules(id),
    task_type text NOT NULL,
    trigger text NOT NULL,
    content text NOT NULL,
    channel text NOT NULL DEFAULT 'telegram',
    delivered_at timestamptz NOT NULL DEFAULT now()
);

-- Index for dedup check: same schedule, same day
CREATE INDEX IF NOT EXISTS idx_proactive_messages_dedup
    ON proactive_messages (schedule_id, delivered_at);

-- Index for schedule lookup
CREATE INDEX IF NOT EXISTS idx_proactive_schedules_enabled
    ON proactive_schedules (org_id, enabled) WHERE enabled = true;

-- Seed schedules for Jordan's org
INSERT INTO proactive_schedules (org_id, name, cron_expression, timezone, task_type, config)
VALUES
    ('1408252a-fd36-4fd3-b527-3b2f495d7b9c', 'morning_briefing', '0 7 * * *', 'America/Chicago', 'morning_briefing', '{"agent_slug": "claw-main"}'),
    ('1408252a-fd36-4fd3-b527-3b2f495d7b9c', 'weekly_review', '0 8 * * 1', 'America/Chicago', 'weekly_review', '{"agent_slug": "claw-main"}'),
    ('1408252a-fd36-4fd3-b527-3b2f495d7b9c', 'daily_scan', '0 7 * * *', 'America/Chicago', 'daily_scan', '{"agent_slug": "claw-main"}')
ON CONFLICT DO NOTHING;

-- Notify PostgREST to pick up new tables
SELECT pg_notify('pgrst', 'reload schema');
```

- [ ] **Step 2: Commit**

```bash
cd jordan-claw && git add migrations/004_proactive_tables.sql
git commit -m "feat: add migration for proactive_schedules, proactive_messages, orgs.telegram_chat_id"
```

Note: Do NOT run this migration yet. It will be run on Supabase after all code is ready and tested.

---

### Task 3: Add croniter Dependency

**Files:**
- Modify: `jordan-claw/pyproject.toml`

- [ ] **Step 1: Add croniter to dependencies**

In `jordan-claw/pyproject.toml`, add `"croniter>=2.0.0",` to the `dependencies` list (after `"caldav>=1.4.0",`).

- [ ] **Step 2: Lock and install**

Run: `cd jordan-claw && uv lock && uv sync`
Expected: Resolves and installs croniter.

- [ ] **Step 3: Commit**

```bash
cd jordan-claw && git add pyproject.toml uv.lock
git commit -m "chore: add croniter dependency for proactive scheduling"
```

---

### Task 4: Proactive Models

Define Pydantic models for schedule configuration and DB records.

**Files:**
- Create: `src/jordan_claw/proactive/__init__.py`
- Create: `src/jordan_claw/proactive/models.py`
- Create: `tests/test_proactive_models.py`

- [ ] **Step 1: Create the proactive package**

Create `src/jordan_claw/proactive/__init__.py` with empty content (just the `from __future__ import annotations` line).

- [ ] **Step 2: Write tests for the models**

Create `tests/test_proactive_models.py`:

```python
from __future__ import annotations

from jordan_claw.proactive.models import ProactiveSchedule


def test_schedule_from_db_row():
    row = {
        "id": "abc-123",
        "org_id": "org-456",
        "name": "morning_briefing",
        "cron_expression": "0 7 * * *",
        "timezone": "America/Chicago",
        "enabled": True,
        "task_type": "morning_briefing",
        "config": {"agent_slug": "claw-main"},
        "last_run_at": None,
        "created_at": "2026-04-05T00:00:00+00:00",
    }
    schedule = ProactiveSchedule.model_validate(row)
    assert schedule.name == "morning_briefing"
    assert schedule.config == {"agent_slug": "claw-main"}
    assert schedule.last_run_at is None


def test_schedule_with_last_run():
    row = {
        "id": "abc-123",
        "org_id": "org-456",
        "name": "weekly_review",
        "cron_expression": "0 8 * * 1",
        "timezone": "America/Chicago",
        "enabled": True,
        "task_type": "weekly_review",
        "config": {"agent_slug": "claw-main"},
        "last_run_at": "2026-04-04T08:00:00+00:00",
        "created_at": "2026-04-01T00:00:00+00:00",
    }
    schedule = ProactiveSchedule.model_validate(row)
    assert schedule.last_run_at is not None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd jordan-claw && uv run pytest tests/test_proactive_models.py -v`
Expected: FAIL — module not found.

- [ ] **Step 4: Write the models**

Create `src/jordan_claw/proactive/models.py`:

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ProactiveSchedule(BaseModel):
    """A row from the proactive_schedules table."""

    id: str
    org_id: str
    name: str
    cron_expression: str
    timezone: str
    enabled: bool
    task_type: str
    config: dict
    last_run_at: datetime | None = None
    created_at: str
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd jordan-claw && uv run pytest tests/test_proactive_models.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd jordan-claw && git add src/jordan_claw/proactive/ tests/test_proactive_models.py
git commit -m "feat: add proactive models and package"
```

---

### Task 5: DB Functions for Proactive Schedules

Add Supabase query functions for schedules and messages.

**Files:**
- Create: `src/jordan_claw/db/proactive.py`
- Create: `tests/test_db_proactive.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_db_proactive.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest


def _mock_db(data: list[dict] | None = None) -> AsyncMock:
    """Build a mock Supabase AsyncClient that returns given data."""
    db = AsyncMock()
    result = MagicMock()
    result.data = data or []

    # Chain: db.table().select().eq().execute()
    chain = MagicMock()
    chain.execute = AsyncMock(return_value=result)
    chain.eq.return_value = chain
    chain.select.return_value = chain
    chain.limit.return_value = chain
    chain.gte.return_value = chain
    chain.lte.return_value = chain
    chain.order.return_value = chain
    db.table.return_value = chain

    return db


@pytest.mark.asyncio
async def test_get_enabled_schedules():
    from jordan_claw.db.proactive import get_enabled_schedules

    rows = [
        {
            "id": "s1",
            "org_id": "org-1",
            "name": "morning_briefing",
            "cron_expression": "0 7 * * *",
            "timezone": "America/Chicago",
            "enabled": True,
            "task_type": "morning_briefing",
            "config": {"agent_slug": "claw-main"},
            "last_run_at": None,
            "created_at": "2026-04-05T00:00:00+00:00",
        }
    ]
    db = _mock_db(rows)
    schedules = await get_enabled_schedules(db)
    assert len(schedules) == 1
    assert schedules[0].name == "morning_briefing"


@pytest.mark.asyncio
async def test_update_last_run():
    from jordan_claw.db.proactive import update_last_run

    db = AsyncMock()
    chain = MagicMock()
    chain.execute = AsyncMock(return_value=MagicMock())
    chain.eq.return_value = chain
    db.table.return_value = MagicMock(update=MagicMock(return_value=chain))

    await update_last_run(db, "s1")
    db.table.assert_called_with("proactive_schedules")


@pytest.mark.asyncio
async def test_insert_proactive_message():
    from jordan_claw.db.proactive import insert_proactive_message

    db = AsyncMock()
    chain = MagicMock()
    chain.execute = AsyncMock(return_value=MagicMock())
    db.table.return_value = MagicMock(insert=MagicMock(return_value=chain))

    await insert_proactive_message(
        db,
        org_id="org-1",
        task_type="morning_briefing",
        trigger="scheduled",
        content="Good morning!",
        schedule_id="s1",
    )
    db.table.assert_called_with("proactive_messages")


@pytest.mark.asyncio
async def test_was_sent_today_returns_true():
    from jordan_claw.db.proactive import was_sent_today

    db = _mock_db([{"id": "msg-1"}])
    result = await was_sent_today(db, "s1", "America/Chicago")
    assert result is True


@pytest.mark.asyncio
async def test_was_sent_today_returns_false():
    from jordan_claw.db.proactive import was_sent_today

    db = _mock_db([])
    result = await was_sent_today(db, "s1", "America/Chicago")
    assert result is False


@pytest.mark.asyncio
async def test_get_telegram_chat_id():
    from jordan_claw.db.proactive import get_telegram_chat_id

    db = _mock_db([{"telegram_chat_id": 12345}])
    chat_id = await get_telegram_chat_id(db, "org-1")
    assert chat_id == 12345


@pytest.mark.asyncio
async def test_get_telegram_chat_id_not_set():
    from jordan_claw.db.proactive import get_telegram_chat_id

    db = _mock_db([{"telegram_chat_id": None}])
    chat_id = await get_telegram_chat_id(db, "org-1")
    assert chat_id is None


@pytest.mark.asyncio
async def test_save_telegram_chat_id():
    from jordan_claw.db.proactive import save_telegram_chat_id

    db = AsyncMock()
    chain = MagicMock()
    chain.execute = AsyncMock(return_value=MagicMock())
    chain.eq.return_value = chain
    db.table.return_value = MagicMock(update=MagicMock(return_value=chain))

    await save_telegram_chat_id(db, "org-1", 12345)
    db.table.assert_called_with("orgs")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jordan-claw && uv run pytest tests/test_db_proactive.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the DB functions**

Create `src/jordan_claw/db/proactive.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import structlog
from supabase._async.client import AsyncClient

from jordan_claw.proactive.models import ProactiveSchedule

log = structlog.get_logger()


async def get_enabled_schedules(client: AsyncClient) -> list[ProactiveSchedule]:
    """Load all enabled proactive schedules."""
    result = (
        await client.table("proactive_schedules")
        .select("*")
        .eq("enabled", True)
        .execute()
    )
    return [ProactiveSchedule.model_validate(row) for row in result.data]


async def update_last_run(client: AsyncClient, schedule_id: str) -> None:
    """Update last_run_at to now for a schedule."""
    await (
        client.table("proactive_schedules")
        .update({"last_run_at": datetime.now(UTC).isoformat()})
        .eq("id", schedule_id)
        .execute()
    )


async def insert_proactive_message(
    client: AsyncClient,
    *,
    org_id: str,
    task_type: str,
    trigger: str,
    content: str,
    schedule_id: str | None = None,
    channel: str = "telegram",
) -> None:
    """Insert an audit row for a sent proactive message."""
    await (
        client.table("proactive_messages")
        .insert(
            {
                "org_id": org_id,
                "schedule_id": schedule_id,
                "task_type": task_type,
                "trigger": trigger,
                "content": content,
                "channel": channel,
            }
        )
        .execute()
    )


async def was_sent_today(
    client: AsyncClient,
    schedule_id: str,
    timezone: str,
) -> bool:
    """Check if a scheduled message was already sent today (in the schedule's timezone)."""
    tz = ZoneInfo(timezone)
    today_start = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_utc = today_start.astimezone(UTC).isoformat()

    result = (
        await client.table("proactive_messages")
        .select("id")
        .eq("schedule_id", schedule_id)
        .gte("delivered_at", today_start_utc)
        .limit(1)
        .execute()
    )
    return len(result.data) > 0


async def get_telegram_chat_id(
    client: AsyncClient,
    org_id: str,
) -> int | None:
    """Look up the Telegram chat ID for an org."""
    result = (
        await client.table("orgs")
        .select("telegram_chat_id")
        .eq("id", org_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return result.data[0].get("telegram_chat_id")


async def save_telegram_chat_id(
    client: AsyncClient,
    org_id: str,
    chat_id: int,
) -> None:
    """Persist the Telegram chat ID on the org record."""
    await (
        client.table("orgs")
        .update({"telegram_chat_id": chat_id})
        .eq("id", org_id)
        .execute()
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd jordan-claw && uv run pytest tests/test_db_proactive.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd jordan-claw && git add src/jordan_claw/db/proactive.py tests/test_db_proactive.py
git commit -m "feat: add DB functions for proactive schedules and messages"
```

---

### Task 6: Message Delivery

Build the `send_proactive_message` function that all executors route through.

**Files:**
- Create: `src/jordan_claw/proactive/delivery.py`
- Create: `tests/test_proactive_delivery.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_proactive_delivery.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_bot() -> AsyncMock:
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    return bot


@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock()


@pytest.mark.asyncio
async def test_send_skips_empty_content(mock_bot, mock_db):
    from jordan_claw.proactive.delivery import send_proactive_message

    await send_proactive_message(
        bot=mock_bot,
        db=mock_db,
        org_id="org-1",
        content="",
        task_type="daily_scan",
        trigger="scheduled",
    )

    mock_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_send_delivers_via_telegram(mock_bot, mock_db):
    from jordan_claw.proactive.delivery import send_proactive_message

    with (
        patch(
            "jordan_claw.proactive.delivery.get_telegram_chat_id",
            new=AsyncMock(return_value=12345),
        ),
        patch(
            "jordan_claw.proactive.delivery.was_sent_today",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "jordan_claw.proactive.delivery.insert_proactive_message",
            new=AsyncMock(),
        ) as mock_insert,
    ):
        await send_proactive_message(
            bot=mock_bot,
            db=mock_db,
            org_id="org-1",
            content="Good morning!",
            task_type="morning_briefing",
            trigger="scheduled",
            schedule_id="s1",
        )

    mock_bot.send_message.assert_called_once_with(12345, "Good morning!")


@pytest.mark.asyncio
async def test_send_skips_if_no_chat_id(mock_bot, mock_db):
    from jordan_claw.proactive.delivery import send_proactive_message

    with patch(
        "jordan_claw.proactive.delivery.get_telegram_chat_id",
        new=AsyncMock(return_value=None),
    ):
        await send_proactive_message(
            bot=mock_bot,
            db=mock_db,
            org_id="org-1",
            content="Hello!",
            task_type="morning_briefing",
            trigger="scheduled",
        )

    mock_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_send_dedup_prevents_double_send(mock_bot, mock_db):
    from jordan_claw.proactive.delivery import send_proactive_message

    with (
        patch(
            "jordan_claw.proactive.delivery.get_telegram_chat_id",
            new=AsyncMock(return_value=12345),
        ),
        patch(
            "jordan_claw.proactive.delivery.was_sent_today",
            new=AsyncMock(return_value=True),
        ),
    ):
        await send_proactive_message(
            bot=mock_bot,
            db=mock_db,
            org_id="org-1",
            content="Good morning!",
            task_type="morning_briefing",
            trigger="scheduled",
            schedule_id="s1",
        )

    mock_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_send_event_triggered_skips_dedup(mock_bot, mock_db):
    """Event-triggered messages (no schedule_id) skip dedup check."""
    from jordan_claw.proactive.delivery import send_proactive_message

    with (
        patch(
            "jordan_claw.proactive.delivery.get_telegram_chat_id",
            new=AsyncMock(return_value=12345),
        ),
        patch(
            "jordan_claw.proactive.delivery.insert_proactive_message",
            new=AsyncMock(),
        ),
    ):
        await send_proactive_message(
            bot=mock_bot,
            db=mock_db,
            org_id="org-1",
            content="Memory updated: X → Y",
            task_type="memory_flag",
            trigger="memory_flag",
            schedule_id=None,
        )

    mock_bot.send_message.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jordan-claw && uv run pytest tests/test_proactive_delivery.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the delivery module**

Create `src/jordan_claw/proactive/delivery.py`:

```python
from __future__ import annotations

import structlog
from aiogram import Bot
from supabase._async.client import AsyncClient

from jordan_claw.db.proactive import (
    get_telegram_chat_id,
    insert_proactive_message,
    was_sent_today,
)

log = structlog.get_logger()


async def send_proactive_message(
    *,
    bot: Bot,
    db: AsyncClient,
    org_id: str,
    content: str,
    task_type: str,
    trigger: str,
    schedule_id: str | None = None,
    timezone: str = "America/Chicago",
) -> None:
    """Send a proactive message via Telegram and log it.

    Skips sending if content is empty, chat ID is not set, or a scheduled
    message was already sent today (dedup).
    """
    if not content:
        return

    chat_id = await get_telegram_chat_id(db, org_id)
    if chat_id is None:
        log.warning("proactive.no_chat_id", org_id=org_id, task_type=task_type)
        return

    # Dedup: only check for scheduled messages (those with a schedule_id)
    if schedule_id and await was_sent_today(db, schedule_id, timezone):
        log.info("proactive.dedup_skipped", schedule_id=schedule_id, task_type=task_type)
        return

    try:
        await bot.send_message(chat_id, content)
    except Exception:
        log.exception("proactive.send_failed", org_id=org_id, task_type=task_type)
        return

    await insert_proactive_message(
        db,
        org_id=org_id,
        task_type=task_type,
        trigger=trigger,
        content=content,
        schedule_id=schedule_id,
    )

    log.info("proactive.sent", org_id=org_id, task_type=task_type, trigger=trigger)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd jordan-claw && uv run pytest tests/test_proactive_delivery.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd jordan-claw && git add src/jordan_claw/proactive/delivery.py tests/test_proactive_delivery.py
git commit -m "feat: add proactive message delivery with dedup"
```

---

### Task 7: Task Executors

Implement the executor functions for morning briefing, weekly review, daily scan, calendar reminder, and memory flag.

**Files:**
- Create: `src/jordan_claw/proactive/executors.py`
- Create: `tests/test_proactive_executors.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_proactive_executors.py`:

```python
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

CHICAGO = ZoneInfo("America/Chicago")


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
    mock_agent = AsyncMock()
    mock_result = MagicMock()
    mock_result.output = "Good morning! Here's your briefing."
    mock_agent.run = AsyncMock(return_value=mock_result)

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
            new=AsyncMock(return_value=(mock_agent, "anthropic:claude-haiku-4-5-20251001")),
        ),
    ):
        result = await execute_morning_briefing(
            mock_db, "org-1", {"agent_slug": "claw-main"}, _mock_settings()
        )

    assert len(result) > 0
    assert result == "Good morning! Here's your briefing."


@pytest.mark.asyncio
async def test_weekly_review_returns_message():
    from jordan_claw.proactive.executors import execute_weekly_review

    mock_db = AsyncMock()
    mock_agent = AsyncMock()
    mock_result = MagicMock()
    mock_result.output = "This week you had 12 meetings."
    mock_agent.run = AsyncMock(return_value=mock_result)

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
            new=AsyncMock(return_value=[{"summary": "Decided on new logo", "created_at": "2026-04-03T10:00:00"}]),
        ),
        patch(
            "jordan_claw.proactive.executors.build_agent",
            new=AsyncMock(return_value=(mock_agent, "anthropic:claude-haiku-4-5-20251001")),
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

    with patch(
        "jordan_claw.proactive.executors.get_calendar_events",
        new=AsyncMock(return_value=events_text),
    ), patch(
        "jordan_claw.proactive.executors._parse_event_times",
        return_value=[
            ("Meeting A", datetime(2026, 4, 5, 9, 0, tzinfo=CHICAGO), datetime(2026, 4, 5, 10, 0, tzinfo=CHICAGO)),
            ("Meeting B", datetime(2026, 4, 5, 9, 30, tzinfo=CHICAGO), datetime(2026, 4, 5, 10, 30, tzinfo=CHICAGO)),
        ],
    ):
        result = await execute_daily_scan(
            AsyncMock(), "org-1", {}, _mock_settings()
        )

    assert "conflict" in result.lower() or "overlap" in result.lower()


@pytest.mark.asyncio
async def test_calendar_reminder_returns_brief():
    from jordan_claw.proactive.executors import execute_calendar_reminder

    mock_db = AsyncMock()
    mock_agent = AsyncMock()
    mock_result = MagicMock()
    mock_result.output = "Meeting with Sarah in 30 min. She's the DGW marketing lead."
    mock_agent.run = AsyncMock(return_value=mock_result)

    with (
        patch(
            "jordan_claw.proactive.executors.load_memory_context",
            new=AsyncMock(return_value="## Memory\n- Sarah: DGW marketing lead"),
        ),
        patch(
            "jordan_claw.proactive.executors.build_agent",
            new=AsyncMock(return_value=(mock_agent, "anthropic:claude-haiku-4-5-20251001")),
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jordan-claw && uv run pytest tests/test_proactive_executors.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the executors**

Create `src/jordan_claw/proactive/executors.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import structlog
from supabase._async.client import AsyncClient

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.agents.factory import build_agent
from jordan_claw.config import Settings
from jordan_claw.db.memory import get_recent_events
from jordan_claw.memory.reader import load_memory_context
from jordan_claw.tools.calendar import get_calendar_events

log = structlog.get_logger()

MORNING_BRIEFING_PROMPT = """\
Compose a concise morning briefing for Jordan. Include:
1. Today's calendar overview (what's coming up, any prep needed)
2. Relevant context from memory

Keep it short and actionable. No fluff.

## Today's Calendar
{calendar}

## Memory Context
{memory}
"""

WEEKLY_REVIEW_PROMPT = """\
Compose a concise weekly review for Jordan. Include:
1. Overview of this week's calendar (meetings, key events)
2. What was learned this week (from memory events)
3. Any patterns or follow-ups worth noting

Keep it short and actionable.

## This Week's Calendar
{calendar}

## Memory Context
{memory}

## This Week's Activity
{events}
"""

CALENDAR_REMINDER_PROMPT = """\
Jordan has a meeting coming up in 30 minutes. Compose a short pre-meeting brief.
Include any relevant context you know about the attendees or topic.

## Meeting
{event_title} at {event_time}

## Memory Context
{memory}
"""


async def _run_agent_prompt(
    db: AsyncClient,
    org_id: str,
    agent_slug: str,
    settings: Settings,
    prompt: str,
) -> str:
    """Build the agent and run a single prompt, returning the output text."""
    agent, _ = await build_agent(db, org_id, agent_slug)
    deps = AgentDeps(
        org_id=org_id,
        tavily_api_key=settings.tavily_api_key,
        fastmail_username=settings.fastmail_username,
        fastmail_app_password=settings.fastmail_app_password,
        supabase_client=db,
        openai_api_key=settings.openai_api_key,
    )
    result = await agent.run(prompt, deps=deps)
    return result.output


async def execute_morning_briefing(
    db: AsyncClient,
    org_id: str,
    config: dict,
    settings: Settings,
) -> str:
    """Compose a morning briefing with today's calendar and memory context."""
    today = datetime.now(ZoneInfo("America/Chicago"))
    today_str = today.strftime("%Y-%m-%d")

    calendar = await get_calendar_events(
        settings.fastmail_username, settings.fastmail_app_password,
        today_str, today_str,
    )
    memory = await load_memory_context(db, org_id)

    prompt = MORNING_BRIEFING_PROMPT.format(calendar=calendar, memory=memory)
    agent_slug = config.get("agent_slug", settings.default_agent_slug)

    return await _run_agent_prompt(db, org_id, agent_slug, settings, prompt)


async def execute_weekly_review(
    db: AsyncClient,
    org_id: str,
    config: dict,
    settings: Settings,
) -> str:
    """Compose a weekly review with this week's calendar, memory, and events."""
    tz = ZoneInfo("America/Chicago")
    today = datetime.now(tz)
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)

    calendar = await get_calendar_events(
        settings.fastmail_username, settings.fastmail_app_password,
        monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d"),
    )
    memory = await load_memory_context(db, org_id)
    recent_events = await get_recent_events(db, org_id, limit=30)

    events_text = "\n".join(
        f"- {e.get('summary', 'Unknown')}" for e in recent_events
    ) or "No notable events this week."

    prompt = WEEKLY_REVIEW_PROMPT.format(
        calendar=calendar, memory=memory, events=events_text,
    )
    agent_slug = config.get("agent_slug", settings.default_agent_slug)

    return await _run_agent_prompt(db, org_id, agent_slug, settings, prompt)


def _parse_event_times(
    events_text: str,
) -> list[tuple[str, datetime, datetime]]:
    """Parse event lines into (title, start, end) tuples.

    Expected format: "- Title: HH:MM - HH:MM" or "- Title: All day"
    Returns empty list for unparseable lines.
    """
    import re

    tz = ZoneInfo("America/Chicago")
    today = datetime.now(tz).date()
    results = []

    for line in events_text.strip().split("\n"):
        match = re.match(r"^- (.+): (\d{2}:\d{2}) - (\d{2}:\d{2})", line)
        if not match:
            continue
        title = match.group(1)
        start_time = datetime.strptime(match.group(2), "%H:%M").time()
        end_time = datetime.strptime(match.group(3), "%H:%M").time()
        start = datetime.combine(today, start_time, tzinfo=tz)
        end = datetime.combine(today, end_time, tzinfo=tz)
        results.append((title, start, end))

    return results


async def execute_daily_scan(
    db: AsyncClient,
    org_id: str,
    config: dict,
    settings: Settings,
) -> str:
    """Scan today's calendar for conflicts. Returns empty string if none found."""
    today = datetime.now(ZoneInfo("America/Chicago"))
    today_str = today.strftime("%Y-%m-%d")

    events_text = await get_calendar_events(
        settings.fastmail_username, settings.fastmail_app_password,
        today_str, today_str,
    )

    if events_text == "No events scheduled.":
        return ""

    events = _parse_event_times(events_text)
    conflicts = []

    for i, (title_a, start_a, end_a) in enumerate(events):
        for title_b, start_b, end_b in events[i + 1 :]:
            if start_a < end_b and start_b < end_a:
                conflicts.append(f"- {title_a} and {title_b} overlap")

    if not conflicts:
        return ""

    return "Calendar conflicts detected:\n" + "\n".join(conflicts)


async def execute_calendar_reminder(
    db: AsyncClient,
    org_id: str,
    config: dict,
    settings: Settings,
    *,
    event_title: str,
    event_time: str,
) -> str:
    """Compose a pre-meeting brief for an upcoming calendar event."""
    memory = await load_memory_context(db, org_id)

    prompt = CALENDAR_REMINDER_PROMPT.format(
        event_title=event_title,
        event_time=event_time,
        memory=memory,
    )
    agent_slug = config.get("agent_slug", settings.default_agent_slug)

    return await _run_agent_prompt(db, org_id, agent_slug, settings, prompt)


def format_memory_flag(old_content: str, new_content: str) -> str:
    """Format a memory correction notification. No agent call needed."""
    return (
        f"I updated my understanding:\n"
        f"Before: {old_content}\n"
        f"Now: {new_content}\n\n"
        f"Let me know if that's wrong."
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd jordan-claw && uv run pytest tests/test_proactive_executors.py -v`
Expected: PASS.

- [ ] **Step 5: Run ruff**

Run: `cd jordan-claw && uv run ruff check src/jordan_claw/proactive/executors.py tests/test_proactive_executors.py --fix`

- [ ] **Step 6: Commit**

```bash
cd jordan-claw && git add src/jordan_claw/proactive/executors.py tests/test_proactive_executors.py
git commit -m "feat: add proactive task executors for briefing, review, scan, reminder, memory flag"
```

---

### Task 8: Scheduler Loop

Build the async scheduler that checks cron schedules and dispatches executors.

**Files:**
- Create: `src/jordan_claw/proactive/scheduler.py`
- Create: `tests/test_proactive_scheduler.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_proactive_scheduler.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jordan_claw.proactive.models import ProactiveSchedule


def _make_schedule(
    task_type: str = "morning_briefing",
    cron: str = "0 7 * * *",
    last_run: datetime | None = None,
    schedule_id: str = "s1",
    timezone: str = "America/Chicago",
) -> ProactiveSchedule:
    return ProactiveSchedule(
        id=schedule_id,
        org_id="org-1",
        name=task_type,
        cron_expression=cron,
        timezone=timezone,
        enabled=True,
        task_type=task_type,
        config={"agent_slug": "claw-main"},
        last_run_at=last_run,
        created_at="2026-04-05T00:00:00+00:00",
    )


def test_should_run_never_run_before():
    from jordan_claw.proactive.scheduler import should_run

    schedule = _make_schedule(last_run=None)
    # If never run and current time is past the cron time, should run
    now = datetime(2026, 4, 5, 13, 0, 0, tzinfo=UTC)  # 8am Central (past 7am)
    assert should_run(schedule, now) is True


def test_should_run_already_ran_today():
    from jordan_claw.proactive.scheduler import should_run

    last_run = datetime(2026, 4, 5, 12, 0, 0, tzinfo=UTC)  # 7am Central today
    schedule = _make_schedule(last_run=last_run)
    now = datetime(2026, 4, 5, 14, 0, 0, tzinfo=UTC)  # 9am Central today
    assert should_run(schedule, now) is False


def test_should_run_missed_run_after_restart():
    from jordan_claw.proactive.scheduler import should_run

    # Last run was yesterday
    last_run = datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC)
    schedule = _make_schedule(last_run=last_run)
    now = datetime(2026, 4, 5, 13, 15, 0, tzinfo=UTC)  # 8:15am Central, past 7am
    assert should_run(schedule, now) is True


def test_should_run_not_yet_time():
    from jordan_claw.proactive.scheduler import should_run

    last_run = datetime(2026, 4, 4, 12, 0, 0, tzinfo=UTC)  # yesterday
    schedule = _make_schedule(last_run=last_run)
    now = datetime(2026, 4, 5, 11, 0, 0, tzinfo=UTC)  # 6am Central, before 7am
    assert should_run(schedule, now) is False


def test_should_run_weekly_correct_day():
    from jordan_claw.proactive.scheduler import should_run

    # Weekly review: Monday 8am Central = "0 8 * * 1"
    schedule = _make_schedule(task_type="weekly_review", cron="0 8 * * 1", last_run=None)
    # 2026-04-06 is a Monday
    now = datetime(2026, 4, 6, 14, 0, 0, tzinfo=UTC)  # 9am Central Monday
    assert should_run(schedule, now) is True


def test_should_run_weekly_wrong_day():
    from jordan_claw.proactive.scheduler import should_run

    schedule = _make_schedule(task_type="weekly_review", cron="0 8 * * 1", last_run=None)
    # 2026-04-05 is a Saturday
    now = datetime(2026, 4, 5, 14, 0, 0, tzinfo=UTC)  # Saturday
    assert should_run(schedule, now) is False


@pytest.mark.asyncio
async def test_dispatch_task_calls_executor():
    from jordan_claw.proactive.scheduler import dispatch_task

    schedule = _make_schedule(task_type="morning_briefing")
    mock_db = AsyncMock()
    mock_bot = AsyncMock()
    mock_settings = MagicMock()

    with (
        patch(
            "jordan_claw.proactive.scheduler.execute_morning_briefing",
            new=AsyncMock(return_value="Good morning!"),
        ) as mock_exec,
        patch(
            "jordan_claw.proactive.scheduler.send_proactive_message",
            new=AsyncMock(),
        ) as mock_send,
        patch(
            "jordan_claw.proactive.scheduler.update_last_run",
            new=AsyncMock(),
        ),
    ):
        await dispatch_task(schedule, mock_db, mock_bot, mock_settings)

    mock_exec.assert_called_once()
    mock_send.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd jordan-claw && uv run pytest tests/test_proactive_scheduler.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the scheduler**

Create `src/jordan_claw/proactive/scheduler.py`:

```python
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import structlog
from aiogram import Bot
from croniter import croniter
from supabase._async.client import AsyncClient

from jordan_claw.config import Settings
from jordan_claw.db.proactive import get_enabled_schedules, update_last_run
from jordan_claw.proactive.delivery import send_proactive_message
from jordan_claw.proactive.executors import (
    execute_daily_scan,
    execute_morning_briefing,
    execute_weekly_review,
)
from jordan_claw.proactive.models import ProactiveSchedule

log = structlog.get_logger()

EXECUTOR_MAP = {
    "morning_briefing": execute_morning_briefing,
    "weekly_review": execute_weekly_review,
    "daily_scan": execute_daily_scan,
}

CHECK_INTERVAL_SECONDS = 60


def should_run(schedule: ProactiveSchedule, now: datetime) -> bool:
    """Determine if a schedule should fire based on its cron expression and last run."""
    tz = ZoneInfo(schedule.timezone)
    now_local = now.astimezone(tz)

    if schedule.last_run_at is None:
        # Never run before: check if we're past the most recent cron time
        cron = croniter(schedule.cron_expression, now_local - __import__("datetime").timedelta(days=1))
        next_time = cron.get_next(datetime)
        return next_time <= now_local
    else:
        last_run_local = schedule.last_run_at.astimezone(tz)
        cron = croniter(schedule.cron_expression, last_run_local)
        next_time = cron.get_next(datetime)
        return next_time <= now_local


async def dispatch_task(
    schedule: ProactiveSchedule,
    db: AsyncClient,
    bot: Bot,
    settings: Settings,
) -> None:
    """Execute a scheduled task and send the result."""
    executor = EXECUTOR_MAP.get(schedule.task_type)
    if not executor:
        log.warning("proactive.unknown_task_type", task_type=schedule.task_type)
        return

    try:
        content = await executor(db, schedule.org_id, schedule.config, settings)

        await send_proactive_message(
            bot=bot,
            db=db,
            org_id=schedule.org_id,
            content=content,
            task_type=schedule.task_type,
            trigger="scheduled",
            schedule_id=schedule.id,
            timezone=schedule.timezone,
        )

        await update_last_run(db, schedule.id)

        log.info(
            "proactive.task_complete",
            task_type=schedule.task_type,
            schedule_id=schedule.id,
            had_content=bool(content),
        )
    except Exception:
        log.exception(
            "proactive.task_failed",
            task_type=schedule.task_type,
            schedule_id=schedule.id,
        )


async def scheduler_loop(
    db: AsyncClient,
    bot: Bot,
    settings: Settings,
) -> None:
    """Main scheduler loop. Runs every 60 seconds, checking for due schedules."""
    log.info("proactive.scheduler_started")

    while True:
        try:
            schedules = await get_enabled_schedules(db)
            now = datetime.now(UTC)

            for schedule in schedules:
                if should_run(schedule, now):
                    asyncio.create_task(
                        dispatch_task(schedule, db, bot, settings),
                        name=f"proactive-{schedule.task_type}-{schedule.id}",
                    )
        except Exception:
            log.exception("proactive.scheduler_tick_failed")

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
```

- [ ] **Step 4: Fix the `should_run` import**

The `should_run` function uses `__import__("datetime").timedelta(days=1)` which is ugly. Replace that line with a proper import. At the top of the file, `timedelta` is not imported. Add it to the datetime import line:

Change:
```python
from datetime import UTC, datetime
```
To:
```python
from datetime import UTC, datetime, timedelta
```

And in `should_run`, replace:
```python
cron = croniter(schedule.cron_expression, now_local - __import__("datetime").timedelta(days=1))
```
With:
```python
cron = croniter(schedule.cron_expression, now_local - timedelta(days=1))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd jordan-claw && uv run pytest tests/test_proactive_scheduler.py -v`
Expected: PASS.

- [ ] **Step 6: Run ruff**

Run: `cd jordan-claw && uv run ruff check src/jordan_claw/proactive/scheduler.py tests/test_proactive_scheduler.py --fix`

- [ ] **Step 7: Commit**

```bash
cd jordan-claw && git add src/jordan_claw/proactive/scheduler.py tests/test_proactive_scheduler.py
git commit -m "feat: add proactive scheduler loop with cron evaluation"
```

---

### Task 9: Wire Scheduler into FastAPI Lifecycle

Start and stop the scheduler loop in `main.py`. Persist `telegram_chat_id` on first incoming message.

**Files:**
- Modify: `src/jordan_claw/main.py`
- Modify: `src/jordan_claw/channels/telegram.py`

- [ ] **Step 1: Update `main.py` to start the scheduler**

In `src/jordan_claw/main.py`, add the scheduler import and start it as a background task alongside the polling task.

Add import at top:
```python
from jordan_claw.proactive.scheduler import scheduler_loop
```

In the `lifespan` function, after `polling_task = asyncio.create_task(start_polling(bot, dp))`, add:

```python
    # Start proactive scheduler
    scheduler_task = asyncio.create_task(
        scheduler_loop(db, bot, settings),
        name="proactive-scheduler",
    )
    logger.info("proactive_scheduler_started")
```

In the shutdown section, after `polling_task.cancel()`, add:

```python
    scheduler_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await scheduler_task
```

- [ ] **Step 2: Update `telegram.py` to persist chat ID**

In `src/jordan_claw/channels/telegram.py`, add the import:
```python
from jordan_claw.db.proactive import save_telegram_chat_id
```

In the `handle_text` function, after `chat_id = str(message.chat.id)`, add:

```python
        # Persist Telegram chat ID for proactive messaging (fire-and-forget)
        asyncio.create_task(
            save_telegram_chat_id(db, default_org_id, message.chat.id),
            name=f"save-chat-id-{message.chat.id}",
        )
```

Also add `import asyncio` at the top of the file.

- [ ] **Step 3: Run ruff on both files**

Run: `cd jordan-claw && uv run ruff check src/jordan_claw/main.py src/jordan_claw/channels/telegram.py --fix`

- [ ] **Step 4: Commit**

```bash
cd jordan-claw && git add src/jordan_claw/main.py src/jordan_claw/channels/telegram.py
git commit -m "feat: wire proactive scheduler into FastAPI lifecycle, persist Telegram chat ID"
```

---

### Task 10: Memory Flag Integration

Hook the memory extractor to send proactive notifications on corrections.

**Files:**
- Modify: `src/jordan_claw/memory/extractor.py`
- Modify: `tests/test_memory_extractor.py`

- [ ] **Step 1: Read current extractor tests**

Run: `cd jordan-claw && cat tests/test_memory_extractor.py`

Understand the existing test patterns before adding new ones.

- [ ] **Step 2: Add a test for the memory flag trigger**

Add to `tests/test_memory_extractor.py`:

```python
@pytest.mark.asyncio
async def test_extract_memory_with_correction_sends_proactive_message():
    """When has_corrections=True and a fact is replaced, a proactive message is sent."""
    from jordan_claw.memory.extractor import extract_memory_background

    mock_db = AsyncMock()

    existing_facts = [
        MemoryFact(
            id="fact-1",
            org_id="org-1",
            category="preference",
            content="Jordan prefers tea",
            source="explicit",
            confidence=0.5,
            created_at="2026-04-01T00:00:00",
            updated_at="2026-04-01T00:00:00",
        )
    ]

    extraction = ExtractionResult(
        facts=[
            ExtractedFact(
                content="Jordan prefers coffee",
                category="preference",
                source="explicit",
                confidence=1.0,
                replaces_fact_id="fact-1",
            )
        ],
        events=[],
        has_corrections=True,
    )

    mock_result = MagicMock()
    mock_result.output = extraction

    with (
        patch("jordan_claw.memory.extractor.get_active_facts", new=AsyncMock(return_value=existing_facts)),
        patch("jordan_claw.memory.extractor.create_extraction_agent") as mock_create,
        patch("jordan_claw.memory.extractor.archive_fact", new=AsyncMock()),
        patch("jordan_claw.memory.extractor.upsert_facts", new=AsyncMock()),
        patch("jordan_claw.memory.extractor.append_events", new=AsyncMock()),
        patch("jordan_claw.memory.extractor.mark_context_stale", new=AsyncMock()),
        patch("jordan_claw.memory.extractor.notify_memory_correction", new=AsyncMock()) as mock_notify,
    ):
        mock_agent = AsyncMock()
        mock_agent.run = AsyncMock(return_value=mock_result)
        mock_create.return_value = mock_agent

        await extract_memory_background(mock_db, "org-1", "I prefer coffee", "Noted!")

    mock_notify.assert_called_once_with(
        mock_db, "org-1", "Jordan prefers tea", "Jordan prefers coffee"
    )
```

Ensure the necessary imports are at the top: `MemoryFact`, `ExtractionResult`, `ExtractedFact`, `ExtractedEvent`.

- [ ] **Step 3: Run test to verify it fails**

Run: `cd jordan-claw && uv run pytest tests/test_memory_extractor.py::test_extract_memory_with_correction_sends_proactive_message -v`
Expected: FAIL — `notify_memory_correction` not found.

- [ ] **Step 4: Add `notify_memory_correction` to the extractor**

In `src/jordan_claw/memory/extractor.py`:

1. Add import at top:
```python
from jordan_claw.proactive.executors import format_memory_flag
```

2. Add the notification function:
```python
async def notify_memory_correction(
    db: AsyncClient,
    org_id: str,
    old_content: str,
    new_content: str,
) -> None:
    """Queue a proactive notification about a memory correction.

    The actual send happens via the delivery module. This function
    is called from extract_memory_background when has_corrections=True.
    """
    from jordan_claw.db.proactive import insert_proactive_message

    content = format_memory_flag(old_content, new_content)
    await insert_proactive_message(
        db,
        org_id=org_id,
        task_type="memory_flag",
        trigger="memory_flag",
        content=content,
    )
```

3. In `extract_memory_background`, after the `if extraction.has_corrections:` block (after `extraction.events.extend(correction_events)`), add:

```python
            # Notify about corrections via proactive messaging
            for fact in extraction.facts:
                if fact.replaces_fact_id:
                    old_fact = next(
                        (f for f in existing_facts if f.id == fact.replaces_fact_id),
                        None,
                    )
                    if old_fact:
                        await notify_memory_correction(
                            db, org_id, old_fact.content, fact.content
                        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd jordan-claw && uv run pytest tests/test_memory_extractor.py::test_extract_memory_with_correction_sends_proactive_message -v`
Expected: PASS.

- [ ] **Step 6: Run all extractor tests to check for regressions**

Run: `cd jordan-claw && uv run pytest tests/test_memory_extractor.py -v`
Expected: All PASS.

- [ ] **Step 7: Commit**

```bash
cd jordan-claw && git add src/jordan_claw/memory/extractor.py tests/test_memory_extractor.py
git commit -m "feat: send proactive notification on memory corrections"
```

---

### Task 11: Calendar Reminder Timers

After the morning briefing runs, set up `asyncio.call_later` timers for 30-min-before calendar reminders.

**Files:**
- Modify: `src/jordan_claw/proactive/scheduler.py`
- Modify: `tests/test_proactive_scheduler.py`

- [ ] **Step 1: Add a test for reminder scheduling**

Add to `tests/test_proactive_scheduler.py`:

```python
@pytest.mark.asyncio
async def test_schedule_calendar_reminders_sets_timers():
    from jordan_claw.proactive.scheduler import schedule_calendar_reminders

    mock_db = AsyncMock()
    mock_bot = AsyncMock()
    mock_settings = MagicMock()
    mock_settings.fastmail_username = "user@test.com"
    mock_settings.fastmail_app_password = "test-pass"

    # An event 2 hours from now
    tz = ZoneInfo("America/Chicago")
    now = datetime.now(tz)
    future_start = now + timedelta(hours=2)
    future_end = future_start + timedelta(hours=1)

    events_text = f"- Big meeting: {future_start.strftime('%H:%M')} - {future_end.strftime('%H:%M')}"

    with (
        patch(
            "jordan_claw.proactive.scheduler.get_calendar_events",
            new=AsyncMock(return_value=events_text),
        ),
        patch(
            "jordan_claw.proactive.scheduler._parse_event_times",
            return_value=[("Big meeting", future_start, future_end)],
        ),
    ):
        timers = await schedule_calendar_reminders(
            mock_db, "org-1", {"agent_slug": "claw-main"}, mock_settings, mock_bot,
        )

    assert len(timers) == 1
```

Add `from datetime import timedelta` and `from zoneinfo import ZoneInfo` imports at top of test file if not present.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd jordan-claw && uv run pytest tests/test_proactive_scheduler.py::test_schedule_calendar_reminders_sets_timers -v`
Expected: FAIL — `schedule_calendar_reminders` not found.

- [ ] **Step 3: Add `schedule_calendar_reminders` to the scheduler**

In `src/jordan_claw/proactive/scheduler.py`, add the import:

```python
from jordan_claw.proactive.executors import _parse_event_times, execute_calendar_reminder
from jordan_claw.tools.calendar import get_calendar_events
```

Add the function:

```python
async def schedule_calendar_reminders(
    db: AsyncClient,
    org_id: str,
    config: dict,
    settings: Settings,
    bot: Bot,
) -> list[asyncio.TimerHandle]:
    """Scan today's events and set 30-min-before reminder timers."""
    tz = ZoneInfo("America/Chicago")
    now = datetime.now(tz)
    today_str = now.strftime("%Y-%m-%d")

    events_text = await get_calendar_events(
        settings.fastmail_username, settings.fastmail_app_password,
        today_str, today_str,
    )

    if events_text == "No events scheduled.":
        return []

    events = _parse_event_times(events_text)
    timers = []
    loop = asyncio.get_running_loop()

    for title, start, end in events:
        remind_at = start - timedelta(minutes=30)
        delay = (remind_at - now).total_seconds()

        if delay <= 0:
            continue

        async def _fire_reminder(t=title, s=start.strftime("%H:%M")):
            try:
                content = await execute_calendar_reminder(
                    db, org_id, config, settings,
                    event_title=t, event_time=s,
                )
                await send_proactive_message(
                    bot=bot,
                    db=db,
                    org_id=org_id,
                    content=content,
                    task_type="calendar_reminder",
                    trigger="calendar_reminder",
                )
            except Exception:
                log.exception("proactive.calendar_reminder_failed", event_title=t)

        handle = loop.call_later(delay, lambda coro=_fire_reminder(): asyncio.create_task(coro()))
        timers.append(handle)
        log.info("proactive.reminder_scheduled", event_title=title, delay_seconds=int(delay))

    return timers
```

Update `dispatch_task` to call `schedule_calendar_reminders` after a morning briefing:

After `await update_last_run(db, schedule.id)`, add:

```python
        # After morning briefing, schedule calendar reminders for today
        if schedule.task_type == "morning_briefing":
            await schedule_calendar_reminders(
                db, schedule.org_id, schedule.config, settings, bot,
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd jordan-claw && uv run pytest tests/test_proactive_scheduler.py -v`
Expected: PASS.

- [ ] **Step 5: Run ruff**

Run: `cd jordan-claw && uv run ruff check src/jordan_claw/proactive/scheduler.py --fix`

- [ ] **Step 6: Commit**

```bash
cd jordan-claw && git add src/jordan_claw/proactive/scheduler.py tests/test_proactive_scheduler.py
git commit -m "feat: schedule 30-min-before calendar reminders after morning briefing"
```

---

### Task 12: Integration Test

Full flow: schedule → scheduler tick → executor → delivery → audit row.

**Files:**
- Create: `tests/test_proactive_integration.py`

- [ ] **Step 1: Write the integration test**

Create `tests/test_proactive_integration.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from jordan_claw.proactive.models import ProactiveSchedule


@pytest.mark.asyncio
async def test_full_scheduled_flow():
    """Scheduler detects a due schedule, runs the executor, sends via delivery."""
    from jordan_claw.proactive.scheduler import dispatch_task

    schedule = ProactiveSchedule(
        id="s-test",
        org_id="org-1",
        name="morning_briefing",
        cron_expression="0 7 * * *",
        timezone="America/Chicago",
        enabled=True,
        task_type="morning_briefing",
        config={"agent_slug": "claw-main"},
        last_run_at=None,
        created_at="2026-04-05T00:00:00+00:00",
    )

    mock_db = AsyncMock()
    mock_bot = AsyncMock()
    mock_bot.send_message = AsyncMock()
    mock_settings = MagicMock()
    mock_settings.fastmail_username = "user@test.com"
    mock_settings.fastmail_app_password = "test-pass"
    mock_settings.openai_api_key = "test-openai"
    mock_settings.tavily_api_key = "test-tavily"
    mock_settings.default_agent_slug = "claw-main"

    inserted_messages = []

    async def capture_insert(client, *, org_id, task_type, trigger, content, schedule_id=None, channel="telegram"):
        inserted_messages.append({
            "org_id": org_id,
            "task_type": task_type,
            "trigger": trigger,
            "content": content,
            "schedule_id": schedule_id,
        })

    with (
        patch(
            "jordan_claw.proactive.executors.get_calendar_events",
            new=AsyncMock(return_value="- Standup: 09:00 - 09:30"),
        ),
        patch(
            "jordan_claw.proactive.executors.load_memory_context",
            new=AsyncMock(return_value=""),
        ),
        patch(
            "jordan_claw.proactive.executors.build_agent",
        ) as mock_build,
        patch(
            "jordan_claw.proactive.delivery.get_telegram_chat_id",
            new=AsyncMock(return_value=12345),
        ),
        patch(
            "jordan_claw.proactive.delivery.was_sent_today",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "jordan_claw.proactive.delivery.insert_proactive_message",
            side_effect=capture_insert,
        ),
        patch(
            "jordan_claw.proactive.scheduler.update_last_run",
            new=AsyncMock(),
        ),
        patch(
            "jordan_claw.proactive.scheduler.schedule_calendar_reminders",
            new=AsyncMock(return_value=[]),
        ),
    ):
        mock_agent = AsyncMock()
        mock_result = MagicMock()
        mock_result.output = "Good morning, Jordan!"
        mock_agent.run = AsyncMock(return_value=mock_result)
        mock_build.return_value = (mock_agent, "test-model")

        await dispatch_task(schedule, mock_db, mock_bot, mock_settings)

    # Verify Telegram message was sent
    mock_bot.send_message.assert_called_once_with(12345, "Good morning, Jordan!")

    # Verify audit row was inserted
    assert len(inserted_messages) == 1
    assert inserted_messages[0]["task_type"] == "morning_briefing"
    assert inserted_messages[0]["trigger"] == "scheduled"
    assert inserted_messages[0]["content"] == "Good morning, Jordan!"
    assert inserted_messages[0]["schedule_id"] == "s-test"
```

- [ ] **Step 2: Run the integration test**

Run: `cd jordan-claw && uv run pytest tests/test_proactive_integration.py -v`
Expected: PASS.

- [ ] **Step 3: Run the full test suite to check for regressions**

Run: `cd jordan-claw && uv run pytest tests/ -v`
Expected: All PASS.

- [ ] **Step 4: Run ruff on all new and modified files**

Run: `cd jordan-claw && uv run ruff check src/jordan_claw/proactive/ src/jordan_claw/tools/calendar.py src/jordan_claw/memory/extractor.py src/jordan_claw/main.py src/jordan_claw/channels/telegram.py tests/ --fix`

- [ ] **Step 5: Commit**

```bash
cd jordan-claw && git add tests/test_proactive_integration.py
git commit -m "test: add proactive messaging integration test"
```

---

### Task 13: Run Migration and Deploy

Run the migration on Supabase and deploy to Railway.

**Files:**
- Modify: `jordan-claw/migrations/004_proactive_tables.sql` (run manually on Supabase)

- [ ] **Step 1: Run the migration on Supabase**

Open the Supabase SQL editor and run the contents of `jordan-claw/migrations/004_proactive_tables.sql`.

Verify:
- `proactive_schedules` table exists with 3 seed rows
- `proactive_messages` table exists
- `orgs` table has `telegram_chat_id` column
- `pg_notify('pgrst', 'reload schema')` ran successfully

- [ ] **Step 2: Push to main and deploy**

```bash
git push origin main
```

Railway auto-deploys from main. Verify the health check passes after deploy.

- [ ] **Step 3: Send a test message to the bot**

Send any message to @jb_homebase_bot on Telegram. This triggers `save_telegram_chat_id` to persist the chat ID. Verify in Supabase that the `orgs` row now has a `telegram_chat_id` value.

- [ ] **Step 4: Verify scheduler is running**

Check Railway logs for `proactive.scheduler_started` log entry. Verify the scheduler loop is checking schedules every 60 seconds.
