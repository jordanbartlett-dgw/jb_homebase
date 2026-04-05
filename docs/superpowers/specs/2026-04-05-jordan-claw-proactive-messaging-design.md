# Jordan Claw Phase 3c: Proactive Messaging — Design Spec

**Date:** 2026-04-05
**Status:** Draft
**Depends on:** Phase 3a (Memory), Phase 3b (Obsidian), Phase 2 (Tool Registry)

## Overview

Add proactive messaging to Jordan Claw so the agent initiates contact rather than only responding. Three message categories:

1. **Scheduled check-ins** — morning briefing (daily) and weekly review (Mondays)
2. **Event-triggered nudges** — calendar reminders (30 min before meetings) and memory fact corrections
3. **Background monitoring** — daily scan for calendar conflicts, runs alongside the morning briefing

All proactive messages deliver via Telegram.

## Prerequisite: Calendar Globals Fix

Deferred decision #4 from Phase 2. The calendar module uses module-level globals for credentials and a cached connection. Background tasks running alongside normal message handling could stomp credentials.

**Changes:**
- Delete `configure_calendar()`, `_reset()`, and all four module globals (`_username`, `_app_password`, `_calendar_cache`, `_cache_lock`)
- `_connect_calendar(username, app_password)` takes credentials as parameters, returns a fresh `caldav.Calendar` each time (no cache — connection is cheap, usage is infrequent)
- `get_calendar_events()` and `create_calendar_event()` gain `username` and `app_password` parameters
- Tool functions (`check_calendar`, `schedule_event`) extract credentials from `ctx.deps` and pass them through
- Tests update to pass credentials explicitly

Pure refactor. No behavior change from callers' perspective.

## Database Schema

### `proactive_schedules`

Defines what proactive tasks exist and when they run.

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid, PK | default `gen_random_uuid()` |
| `org_id` | uuid, FK → orgs | |
| `name` | text | e.g. "morning_briefing", "weekly_review" |
| `cron_expression` | text | e.g. "0 7 * * *", "0 8 * * 1" |
| `timezone` | text | e.g. "America/Chicago" |
| `enabled` | boolean | default true |
| `task_type` | text | one of: "morning_briefing", "weekly_review", "daily_scan" |
| `config` | jsonb | task-specific params (e.g. agent slug) |
| `last_run_at` | timestamptz | null until first execution |
| `created_at` | timestamptz | default `now()` |

### `proactive_messages`

Audit trail of every proactive message sent. Also used for dedup.

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid, PK | default `gen_random_uuid()` |
| `org_id` | uuid, FK → orgs | |
| `schedule_id` | uuid, FK → proactive_schedules, nullable | null for event-triggered messages |
| `task_type` | text | what generated this message |
| `trigger` | text | "scheduled", "calendar_reminder", "memory_flag" |
| `content` | text | the message that was sent |
| `channel` | text | "telegram" |
| `delivered_at` | timestamptz | default `now()` |

### `orgs` table change

Add `telegram_chat_id` column (bigint, nullable). Populated on first incoming Telegram message. The proactive sender reads it from the org record to know where to send messages.

No RLS needed (single tenant).

## Scheduler Loop

A lightweight async loop running inside the FastAPI process.

**Lifecycle:**
- Starts on `FastAPI.on_startup` (same pattern as Telegram bot webhook setup)
- Runs as a background `asyncio.Task`
- Checks the DB every 60 seconds
- Stops on shutdown via `asyncio.Task.cancel()`

**Each tick:**
1. Query `proactive_schedules` where `enabled = true`
2. For each schedule, use `croniter` to compute next run time from `last_run_at`
3. If `next_run <= now`, dispatch the task (async), update `last_run_at`
4. Catch and log exceptions per-task — one failure does not block others

**Restart recovery:** If the process was down during the 7am briefing and comes back at 7:15am, `croniter` computes that the next run is past due and fires immediately.

**Calendar reminders (event-triggered):** After the morning briefing runs, it scans today's calendar events. For each event starting more than 30 minutes from now, it schedules an in-memory `asyncio.call_later` timer to send a reminder 30 minutes before. These timers are ephemeral — lost on restart. Acceptable for v1.

**Memory flag (event-triggered):** The existing `extract_memory_background()` already runs after each conversation turn. When it detects `has_corrections=true`, it additionally calls the proactive message sender. Small addition to existing code, not a new loop.

**New dependency:** `croniter`

## Task Executors

Each `task_type` maps to an executor function with a consistent signature:

```python
async def execute_morning_briefing(
    db: AsyncClient, org_id: str, config: dict, settings: Settings
) -> str
```

Executors receive a `Settings` instance from the scheduler for credential access (Fastmail, OpenAI, Anthropic). They return message text. The scheduler handles delivery.

### `morning_briefing`

1. Fetch today's calendar events via `get_calendar_events()` (credentials from settings, not globals)
2. Fetch memory context via `read_memory_context()`
3. Build a prompt with calendar + memory context
4. Run through the agent (using `build_agent` + agent slug from `config`) to compose a natural-language briefing
5. After sending, scan today's events and set `asyncio.call_later` timers for 30-min-before reminders

### `weekly_review`

1. Fetch this week's calendar events (Monday through Sunday)
2. Fetch memory context
3. Fetch recent `memory_events` (what was learned this week)
4. Run through the agent to compose a weekly summary

### `daily_scan`

1. Fetch today's calendar events, check for overlapping times
2. If conflicts found, compose a message about them
3. Returns empty string if nothing actionable — quiet monitoring only

### `calendar_reminder` (fired by timer, not scheduled)

1. Receives event details (title, time, attendees)
2. Queries memory for facts about attendees
3. Queries Obsidian notes for relevant context
4. Runs through the agent to compose a short pre-meeting brief

### `memory_flag` (fired from extractor, not scheduled)

1. Receives correction details from `ExtractionResult`
2. Composes a template notification: "I updated my understanding: [old fact] → [new fact]. Let me know if that's wrong."
3. No agent call needed

## Message Delivery

Single function all executors and triggers route through:

```python
async def send_proactive_message(
    bot: Bot,
    db: AsyncClient,
    org_id: str,
    content: str,
    task_type: str,
    trigger: str,
    schedule_id: str | None = None,
) -> None
```

The `Bot` instance (aiogram) is passed from the scheduler, which receives it at startup from `main.py` (same instance used for webhook handling).

**Flow:**
1. If `content` is empty, return (nothing to report)
2. Look up `telegram_chat_id` from the org record
3. Send via `bot.send_message(chat_id, content)`
4. Insert row into `proactive_messages` for audit

**Dedup:** Before sending a scheduled message, check `proactive_messages` for a row with the same `schedule_id` and `delivered_at` on the same calendar day. Prevents double-sends on rapid restart.

## File Organization

```
src/jordan_claw/proactive/
├── __init__.py
├── scheduler.py      # Scheduler loop, startup/shutdown hooks
├── executors.py      # morning_briefing, weekly_review, daily_scan, calendar_reminder
├── delivery.py       # send_proactive_message, chat ID resolution, dedup
└── models.py         # Pydantic models for schedule config, message records
```

**Touched existing files:**
- `tools/calendar.py` — remove globals, pass credentials through parameters
- `memory/extractor.py` — add memory_flag trigger when `has_corrections=true`
- `main.py` — start/stop scheduler loop on app lifecycle
- `channels/telegram.py` — persist `telegram_chat_id` on first incoming message

**New migration:** `004_proactive_tables.sql`

**Seed data:** Two schedule rows for Jordan's org:
- Morning briefing: `0 7 * * *` (7:00 AM Central, daily)
- Weekly review: `0 8 * * 1` (8:00 AM Central, Mondays)

## Testing Strategy

**Unit tests:**
- `test_calendar_no_globals.py` — calendar functions work with explicit credentials, no module state
- `test_scheduler.py` — cron evaluation logic: should-fire checks, missed-run recovery, dedup
- `test_executors.py` — each executor with mocked DB/calendar/memory, verify prompt construction
- `test_delivery.py` — send_proactive_message with mocked Telegram bot, verify dedup

**Integration test:**
- `test_proactive_integration.py` — insert schedule row, advance time, verify scheduler fires executor and message row lands in `proactive_messages`

All tests use Pydantic AI `"test"` model. Calendar and Telegram bot are mocked. Supabase calls mocked at client level.
