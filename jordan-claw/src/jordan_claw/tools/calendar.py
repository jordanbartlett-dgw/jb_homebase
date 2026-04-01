from __future__ import annotations

import asyncio
import datetime as dt_module
from datetime import datetime
from zoneinfo import ZoneInfo

import caldav
import icalendar
import structlog

log = structlog.get_logger()

CENTRAL_TZ = ZoneInfo("America/Chicago")

_username: str | None = None
_app_password: str | None = None
_calendar_cache: caldav.Calendar | None = None
_cache_lock: asyncio.Lock | None = None


def _get_lock() -> asyncio.Lock:
    """Return the module-level lock, creating it lazily inside the running loop."""
    global _cache_lock
    if _cache_lock is None:
        _cache_lock = asyncio.Lock()
    return _cache_lock


def configure_calendar(username: str, app_password: str) -> None:
    """Store Fastmail CalDAV credentials for later use."""
    global _username, _app_password, _calendar_cache
    _username = username
    _app_password = app_password
    _calendar_cache = None  # reset cache when credentials change


def _reset() -> None:
    """Clear module-level cache and credentials. Intended for use in tests."""
    global _username, _app_password, _calendar_cache, _cache_lock
    _username = None
    _app_password = None
    _calendar_cache = None
    _cache_lock = None


def _connect_calendar() -> caldav.Calendar:
    """Connect to Fastmail CalDAV and return the default calendar (no caching).

    This runs inside asyncio.to_thread() only when the cache is empty.
    """
    if not _username or not _app_password:
        raise RuntimeError("Calendar credentials not configured. Call configure_calendar() first.")

    url = f"https://caldav.fastmail.com/dav/calendars/user/{_username}/"
    client = caldav.DAVClient(url=url, username=_username, password=_app_password)
    principal = client.principal()
    calendars = principal.calendars()

    if not calendars:
        raise RuntimeError("No calendars found on Fastmail account.")

    # Fastmail puts the default calendar first; Jordan has only one calendar.
    return calendars[0]


async def _get_calendar_async() -> caldav.Calendar:
    """Return the cached calendar connection, connecting if necessary.

    Uses an asyncio.Lock to prevent concurrent threads from racing to populate
    the cache when called via asyncio.to_thread().
    """
    global _calendar_cache

    if not _username or not _app_password:
        raise RuntimeError("Calendar credentials not configured. Call configure_calendar() first.")

    async with _get_lock():
        if _calendar_cache is not None:
            return _calendar_cache
        _calendar_cache = await asyncio.to_thread(_connect_calendar)
        return _calendar_cache


def _format_dt(dt: datetime | dt_module.date) -> str:
    """Return HH:MM in Central time, or 'All day' for date-only values."""
    # CalDAV can return bare date objects for all-day events.
    if type(dt) is dt_module.date:
        return "All day"
    dt = dt.replace(tzinfo=CENTRAL_TZ) if dt.tzinfo is None else dt.astimezone(CENTRAL_TZ)
    return dt.strftime("%H:%M")


async def get_calendar_events(start_date: datetime, end_date: datetime) -> str:
    """Query CalDAV for events in a date range and return formatted text."""
    # Ensure search bounds are timezone-aware so CalDAV comparisons work correctly.
    if start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=CENTRAL_TZ)
    if end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=CENTRAL_TZ)

    try:
        calendar = await _get_calendar_async()
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


def _build_ical(
    title: str,
    start: datetime,
    end: datetime,
    location: str | None = None,
    description: str | None = None,
) -> str:
    """Build a well-formed iCal string using the icalendar library.

    Using icalendar (caldav's own transitive dep) ensures correct encoding,
    line folding per RFC 5545, and proper VTIMEZONE handling.
    """
    cal = icalendar.Calendar()
    cal.add("PRODID", "-//jordan-claw//EN")
    cal.add("VERSION", "2.0")

    event = icalendar.Event()
    event.add("SUMMARY", title)
    event.add("DTSTART", start.astimezone(ZoneInfo("UTC")))
    event.add("DTEND", end.astimezone(ZoneInfo("UTC")))
    if location:
        event.add("LOCATION", location)
    if description:
        event.add("DESCRIPTION", description)

    cal.add_component(event)
    return cal.to_ical().decode()


async def create_calendar_event(
    title: str,
    start: str | datetime,
    end: str | datetime,
    location: str | None = None,
    description: str | None = None,
) -> str:
    """Create a CalDAV event and return a confirmation string.

    Accepts ISO 8601 strings or datetime objects for start/end. Naive datetimes
    are treated as Central time, which matches what the agent passes.
    """
    if isinstance(start, str):
        start = datetime.fromisoformat(start)
    if isinstance(end, str):
        end = datetime.fromisoformat(end)

    # Agent passes ISO strings without timezone info (e.g. "2026-04-02T14:00:00").
    if start.tzinfo is None:
        start = start.replace(tzinfo=CENTRAL_TZ)
    if end.tzinfo is None:
        end = end.replace(tzinfo=CENTRAL_TZ)

    try:
        calendar = await _get_calendar_async()
        ical = _build_ical(title, start, end, location, description)
        await asyncio.to_thread(calendar.save_event, ical)
    except Exception as exc:
        log.error("calendar.create_event.failed", error=str(exc))
        return f"Error creating calendar event: {exc}"

    start_central = start.astimezone(CENTRAL_TZ)
    end_central = end.astimezone(CENTRAL_TZ)
    date_str = start_central.strftime("%Y-%m-%d")
    start_str = start_central.strftime("%H:%M")
    end_str = end_central.strftime("%H:%M")
    return f"Created: {title} on {date_str} from {start_str} to {end_str}"
