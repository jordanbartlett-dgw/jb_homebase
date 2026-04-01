from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import caldav
import structlog

log = structlog.get_logger()

CHICAGO = ZoneInfo("America/Chicago")

_username: str | None = None
_app_password: str | None = None
_calendar_cache: caldav.Calendar | None = None


def configure_calendar(username: str, app_password: str) -> None:
    """Store Fastmail CalDAV credentials for later use."""
    global _username, _app_password, _calendar_cache
    _username = username
    _app_password = app_password
    _calendar_cache = None  # reset cache when credentials change


def _get_calendar() -> caldav.Calendar:
    """Connect to Fastmail CalDAV and return the default calendar, with caching."""
    global _calendar_cache

    if _calendar_cache is not None:
        return _calendar_cache

    if not _username or not _app_password:
        raise RuntimeError("Calendar credentials not configured. Call configure_calendar() first.")

    url = f"https://caldav.fastmail.com/dav/calendars/user/{_username}/"
    client = caldav.DAVClient(url=url, username=_username, password=_app_password)
    principal = client.principal()
    calendars = principal.calendars()

    if not calendars:
        raise RuntimeError("No calendars found on Fastmail account.")

    _calendar_cache = calendars[0]
    return _calendar_cache


def _format_dt(dt: datetime) -> str:
    """Return HH:MM in Chicago time."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=CHICAGO)
    else:
        dt = dt.astimezone(CHICAGO)
    return dt.strftime("%H:%M")


async def get_calendar_events(start_date: datetime, end_date: datetime) -> str:
    """Query CalDAV for events in a date range and return formatted text."""
    try:
        calendar = await asyncio.to_thread(_get_calendar)
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
    """Build a minimal iCal string for a single event."""

    def fmt(dt: datetime) -> str:
        # CalDAV expects UTC or floating local; use UTC
        return dt.astimezone(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ")

    uid = str(uuid.uuid4())
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//jordan-claw//EN",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"SUMMARY:{title}",
        f"DTSTART:{fmt(start)}",
        f"DTEND:{fmt(end)}",
    ]
    if location:
        lines.append(f"LOCATION:{location}")
    if description:
        lines.append(f"DESCRIPTION:{description}")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(lines)


async def create_calendar_event(
    title: str,
    start: datetime,
    end: datetime,
    location: str | None = None,
    description: str | None = None,
) -> str:
    """Create a CalDAV event and return a confirmation string."""
    try:
        calendar = await asyncio.to_thread(_get_calendar)
        ical = _build_ical(title, start, end, location, description)
        await asyncio.to_thread(calendar.save_event, ical)
    except Exception as exc:
        log.error("calendar.create_event.failed", error=str(exc))
        return f"Error creating calendar event: {exc}"

    start_central = start.astimezone(CHICAGO)
    end_central = end.astimezone(CHICAGO)
    date_str = start_central.strftime("%Y-%m-%d")
    start_str = start_central.strftime("%H:%M")
    end_str = end_central.strftime("%H:%M")
    return f"Created: {title} on {date_str} from {start_str} to {end_str}"
