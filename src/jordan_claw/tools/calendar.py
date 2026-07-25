from __future__ import annotations

import asyncio
import datetime as dt_module
from datetime import datetime
from zoneinfo import ZoneInfo

import caldav
import icalendar
import structlog
from pydantic import BaseModel
from pydantic_ai import RunContext

from jordan_claw.agents.deps import AgentDeps

log = structlog.get_logger()

CENTRAL_TZ = ZoneInfo("America/Chicago")

# Discovered calendar URL per username. Skips the principal + calendar-list
# discovery round trips on repeat calls; the DAVClient itself is still built
# per call so credentials never leak across orgs.
_calendar_url_cache: dict[str, str] = {}


class CalendarAccessError(RuntimeError):
    """Calendar service could not be reached or queried."""


class CalendarEvent(BaseModel):
    """Structured calendar event shared by app responses and agent formatting."""

    id: str
    title: str
    starts_at: datetime
    ends_at: datetime
    all_day: bool
    location: str | None = None


def _connect_calendar(username: str, app_password: str) -> caldav.Calendar:
    """Connect to Fastmail CalDAV and return the default calendar."""
    url = f"https://caldav.fastmail.com/dav/calendars/user/{username}/"
    client = caldav.DAVClient(url=url, username=username, password=app_password)

    cached_url = _calendar_url_cache.get(username)
    if cached_url:
        return client.calendar(url=cached_url)

    principal = client.principal()
    calendars = principal.calendars()

    if not calendars:
        raise RuntimeError("No calendars found on Fastmail account.")

    # Fastmail puts the default calendar first; Jordan has only one calendar.
    calendar = calendars[0]
    _calendar_url_cache[username] = str(calendar.url)
    return calendar


def _format_dt(dt: datetime | dt_module.date) -> str:
    """Return HH:MM in Central time, or 'All day' for date-only values."""
    # CalDAV can return bare date objects for all-day events.
    if type(dt) is dt_module.date:
        return "All day"
    dt = dt.replace(tzinfo=CENTRAL_TZ) if dt.tzinfo is None else dt.astimezone(CENTRAL_TZ)
    return dt.strftime("%H:%M")


def _normalize_range_boundary(value: str | datetime, *, end: bool) -> datetime:
    if isinstance(value, str):
        parsed = datetime.strptime(value, "%Y-%m-%d")
        if end:
            parsed = parsed.replace(hour=23, minute=59, second=59)
        value = parsed
    return value.replace(tzinfo=CENTRAL_TZ) if value.tzinfo is None else value


def _event_datetime(value: datetime | dt_module.date) -> datetime:
    if type(value) is dt_module.date:
        return datetime.combine(value, dt_module.time.min, tzinfo=CENTRAL_TZ)
    if value.tzinfo is None:
        return value.replace(tzinfo=CENTRAL_TZ)
    return value.astimezone(CENTRAL_TZ)


def _component_text(component, key: str) -> str | None:
    if key not in component:
        return None
    value = component[key]
    encoded = value.to_ical()
    return encoded.decode() if isinstance(encoded, bytes) else str(encoded)


async def list_calendar_events(
    username: str,
    app_password: str,
    start_date: str | datetime,
    end_date: str | datetime,
) -> list[CalendarEvent]:
    """Query CalDAV for structured events in a date range.

    Raises CalendarAccessError when Fastmail cannot be reached. Malformed
    individual events are logged and skipped so one bad entry does not hide
    the rest of the agenda.
    """
    start_date = _normalize_range_boundary(start_date, end=False)
    end_date = _normalize_range_boundary(end_date, end=True)

    try:
        calendar = await asyncio.to_thread(_connect_calendar, username, app_password)
        items = await asyncio.to_thread(calendar.search, start=start_date, end=end_date, event=True)
    except Exception as exc:
        log.error("calendar.get_events.failed", error=str(exc))
        raise CalendarAccessError("Calendar is temporarily unavailable.") from exc

    events: list[CalendarEvent] = []
    for item in items:
        try:
            for comp in item.icalendar_instance.walk():
                if comp.name != "VEVENT":
                    continue
                title = _component_text(comp, "SUMMARY") or "Untitled event"
                raw_start = comp["DTSTART"].dt
                if "DTEND" in comp:
                    raw_end = comp["DTEND"].dt
                elif type(raw_start) is dt_module.date:
                    raw_end = raw_start + dt_module.timedelta(days=1)
                else:
                    raw_end = raw_start + dt_module.timedelta(hours=1)
                all_day = type(raw_start) is dt_module.date
                starts_at = _event_datetime(raw_start)
                ends_at = _event_datetime(raw_end)
                uid = _component_text(comp, "UID")
                events.append(
                    CalendarEvent(
                        id=uid or f"{title}-{starts_at.isoformat()}",
                        title=title,
                        starts_at=starts_at,
                        ends_at=ends_at,
                        all_day=all_day,
                        location=_component_text(comp, "LOCATION") or None,
                    )
                )
        except Exception as exc:
            log.warning("calendar.parse_event.failed", error=str(exc))
            continue

    return sorted(events, key=lambda event: event.starts_at)


async def get_calendar_events(
    username: str,
    app_password: str,
    start_date: str | datetime,
    end_date: str | datetime,
) -> str:
    """Query CalDAV and return the formatted text expected by agent tools."""
    try:
        events = await list_calendar_events(username, app_password, start_date, end_date)
    except CalendarAccessError as exc:
        return f"Error fetching calendar events: {exc}"

    if not events:
        return "No events scheduled."

    lines = []
    for event in events:
        if event.all_day:
            line = f"- {event.title}: All day"
        else:
            line = (
                f"- {event.title}: "
                f"{event.starts_at.astimezone(CENTRAL_TZ).strftime('%H:%M')} - "
                f"{event.ends_at.astimezone(CENTRAL_TZ).strftime('%H:%M')}"
            )
        if event.location:
            line += f" ({event.location})"
        lines.append(line)
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
    username: str,
    app_password: str,
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
        calendar = await asyncio.to_thread(_connect_calendar, username, app_password)
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


async def check_calendar(ctx: RunContext[AgentDeps], start_date: str, end_date: str) -> str:
    """Check Jordan's calendar for events in a date range.

    Args:
        start_date: Start date as YYYY-MM-DD
        end_date: End date as YYYY-MM-DD
    """
    return await get_calendar_events(
        ctx.deps.fastmail_username, ctx.deps.fastmail_app_password, start_date, end_date
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
        ctx.deps.fastmail_username,
        ctx.deps.fastmail_app_password,
        title,
        start,
        end,
        location,
        description,
    )
