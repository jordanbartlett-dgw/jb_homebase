# Jordan Claw: Fastmail Calendar Integration

**Date:** 2026-04-01
**Status:** Approved
**Scope:** Add CalDAV calendar tools to Jordan Claw for reading and creating events on Jordan's Fastmail calendar

## Context

Jordan Claw Phase 1 MVP is deployed: Telegram bot, single Pydantic AI agent, Supabase persistence, web search + datetime tools. The next step is making Claw useful as a personal assistant by giving it access to Jordan's Fastmail calendar.

This is the first "personal org" capability. Jordan is new to Fastmail, so Claw will likely be the primary calendar interface.

## Approach

Direct CalDAV client using the `caldav` Python library. No MCP server, no JMAP. Fastmail's CalDAV endpoint is stable and the library is mature. Single calendar, single user.

## CalDAV Connection & Auth

- Endpoint: `https://caldav.fastmail.com/dav/calendars/user@fastmail.com/`
- Auth: app-specific password (already generated and stored in Infisical)
- Two new env vars added to `Settings` in `config.py`:
  - `FASTMAIL_USERNAME` — Fastmail email address
  - `FASTMAIL_APP_PASSWORD` — app-specific password
- Thin `CalendarClient` class in `src/jordan_claw/tools/calendar.py`
  - Initializes CalDAV connection
  - Caches the single calendar reference
  - Sync `caldav` calls wrapped in `asyncio.to_thread()`

## Agent Tools

Two new Pydantic AI tools registered in `agents/factory.py`:

### `get_calendar_events(start_date: str, end_date: str) -> str`

- Takes ISO date strings for range
- Agent resolves natural language dates (e.g. "tomorrow", "Friday") using `current_datetime` tool
- Queries CalDAV for events in range
- Returns formatted summary: title, start time, end time, location (if set)
- Empty calendar returns "No events scheduled"

### `create_calendar_event(title: str, start: str, end: str, location: str | None, description: str | None) -> str`

- Creates iCalendar event via CalDAV
- `start` and `end` are ISO datetime strings
- Agent calculates end time when user specifies duration (e.g. "30 minutes")
- Returns confirmation: "Created: {title} on {date} from {start} to {end}"
- No confirmation step for MVP. Claw creates the event immediately.

### System Prompt Update

Short addition to the agent system prompt explaining:
- Claw can read and create calendar events
- Use `current_datetime` first to resolve relative dates before calling calendar tools

## Data Flow

### Creating an event

1. User: "Meeting with Sarah tomorrow at 2pm for 30 minutes"
2. Agent calls `current_datetime` to resolve "tomorrow"
3. Agent calls `create_calendar_event(title="Meeting with Sarah", start="2026-04-02T14:00:00", end="2026-04-02T14:30:00")`
4. Tool creates event via CalDAV, returns confirmation
5. Agent responds with human-readable confirmation

### Reading events

1. User: "What's on my calendar Friday?"
2. Agent calls `current_datetime`, then `get_calendar_events(start_date="2026-04-03", end_date="2026-04-03")`
3. Tool queries CalDAV, returns formatted list
4. Agent summarizes events to user

## Error Handling

- CalDAV connection failure: tool returns error string to agent, agent tells user it could not reach the calendar. No crash.
- Invalid date inputs: agent handles natural language parsing, malformed ISO strings caught by tool and returned as error string.
- Follows existing pattern: errors logged via structlog, agent gets error string, user gets human response. No exceptions bubble to gateway.

## Testing

Mocked CalDAV client, no live Fastmail calls. Follows existing test patterns.

- `test_get_events_returns_formatted_list` — mock returns two events, verify formatted output
- `test_get_events_empty_calendar` — mock returns no events, verify "No events scheduled"
- `test_create_event_success` — mock save, verify confirmation string and iCal data
- `test_create_event_with_optional_fields` — location and description in iCal event
- `test_caldav_connection_error` — mock failure, verify error string returned

## Dependencies

- `caldav` — CalDAV client library (new dependency)

## Future (not in this spec)

- Find availability: "Find me a time this week to meet with Sarah"
- Event updates and cancellation
- Recurring events
- Multiple calendars
