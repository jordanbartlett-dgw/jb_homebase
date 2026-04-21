from __future__ import annotations

import asyncio
import datetime as dt_module
from datetime import datetime
from zoneinfo import ZoneInfo

import caldav
import icalendar
import structlog
from pydantic_ai import RunContext

from jordan_claw.agents.deps import AgentDeps

log = structlog.get_logger()

CENTRAL_TZ = ZoneInfo("America/Chicago")


def _connect_calendar(username: str, app_password: str) -> caldav.Calendar:
    """Connect to Fastmail CalDAV and return the default calendar."""
    url = f"https://caldav.fastmail.com/dav/calendars/user/{username}/"
    client = caldav.DAVClient(url=url, username=username, password=app_password)
    principal = client.principal()
    calendars = principal.calendars()

    if not calendars:
        raise RuntimeError("No calendars found on Fastmail account.")

    # Fastmail puts the default calendar first; Jordan has only one calendar.
    return calendars[0]


def _format_dt(dt: datetime | dt_module.date) -> str:
    """Return HH:MM in Central time, or 'All day' for date-only values."""
    # CalDAV can return bare date objects for all-day events.
    if type(dt) is dt_module.date:
        return "All day"
    dt = dt.replace(tzinfo=CENTRAL_TZ) if dt.tzinfo is None else dt.astimezone(CENTRAL_TZ)
    return dt.strftime("%H:%M")


async def get_calendar_events(
    username: str,
    app_password: str,
    start_date: str | datetime,
    end_date: str | datetime,
) -> str:
    """Query CalDAV for events in a date range and return formatted text.

    Accepts ISO date strings (YYYY-MM-DD) or datetime objects.
    """
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
        ctx.deps.fastmail_username, ctx.deps.fastmail_app_password,
        title, start, end, location, description,
    )
