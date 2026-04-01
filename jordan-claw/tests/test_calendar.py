from __future__ import annotations

import datetime as dt_module
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

CHICAGO = ZoneInfo("America/Chicago")


@pytest.fixture(autouse=True)
def reset_calendar_module():
    """Reset module-level cache and credentials before each test."""
    from jordan_claw.tools.calendar import _reset

    _reset()
    yield
    _reset()


def _make_vevent(
    summary: str,
    start: datetime,
    end: datetime,
    location: str | None = None,
) -> MagicMock:
    """Build a mock VEVENT component."""
    comp = MagicMock()
    comp.name = "VEVENT"

    comp.__getitem__ = MagicMock(
        side_effect=lambda key: {
            "SUMMARY": _ical_str(summary),
            "DTSTART": _ical_dt(start),
            "DTEND": _ical_dt(end),
            **({"LOCATION": _ical_str(location)} if location else {}),
        }[key]
    )
    comp.__contains__ = MagicMock(
        side_effect=lambda key: (
            key in (["SUMMARY", "DTSTART", "DTEND"] + (["LOCATION"] if location else []))
        )
    )
    return comp


def _ical_str(value: str) -> MagicMock:
    m = MagicMock()
    m.to_ical.return_value = value.encode()
    return m


def _ical_dt(value: datetime) -> MagicMock:
    m = MagicMock()
    m.dt = value
    return m


def _make_calendar_item(vevents: list[MagicMock]) -> MagicMock:
    """Build a mock calendar item whose .icalendar_instance.walk() yields given vevents."""
    item = MagicMock()
    # walk() returns all components; only VEVENT ones are processed
    item.icalendar_instance.walk.return_value = vevents
    return item


def _make_mock_calendar(items: list[MagicMock]) -> MagicMock:
    cal = MagicMock()
    cal.search.return_value = items
    return cal


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
        "jordan_claw.tools.calendar._get_calendar_async",
        new=AsyncMock(return_value=mock_cal),
    ):
        result = await get_calendar_events(
            datetime(2026, 4, 1, tzinfo=CHICAGO),
            datetime(2026, 4, 2, tzinfo=CHICAGO),
        )

    assert "Team standup" in result
    assert "09:00" in result
    assert "10:00" in result
    assert "Client call" in result
    assert "14:00" in result
    assert "15:30" in result


@pytest.mark.asyncio
async def test_get_events_empty_calendar():
    from jordan_claw.tools.calendar import get_calendar_events

    mock_cal = _make_mock_calendar([])

    with patch(
        "jordan_claw.tools.calendar._get_calendar_async",
        new=AsyncMock(return_value=mock_cal),
    ):
        result = await get_calendar_events(
            datetime(2026, 4, 1, tzinfo=CHICAGO),
            datetime(2026, 4, 2, tzinfo=CHICAGO),
        )

    assert result == "No events scheduled."


@pytest.mark.asyncio
async def test_create_event_success():
    from jordan_claw.tools.calendar import create_calendar_event

    start = datetime(2026, 4, 5, 10, 0, tzinfo=CHICAGO)
    end = datetime(2026, 4, 5, 11, 0, tzinfo=CHICAGO)

    mock_cal = MagicMock()
    mock_cal.save_event.return_value = None

    with patch(
        "jordan_claw.tools.calendar._get_calendar_async",
        new=AsyncMock(return_value=mock_cal),
    ):
        result = await create_calendar_event("Budget review", start, end)

    assert "Created" in result
    assert "Budget review" in result
    assert "2026-04-05" in result
    assert "10:00" in result
    assert "11:00" in result

    # Verify save_event was called with iCal data containing VCALENDAR
    mock_cal.save_event.assert_called_once()
    ical_arg = mock_cal.save_event.call_args[0][0]
    assert "VCALENDAR" in ical_arg
    assert "VEVENT" in ical_arg
    assert "Budget review" in ical_arg


@pytest.mark.asyncio
async def test_create_event_with_optional_fields():
    from jordan_claw.tools.calendar import create_calendar_event

    start = datetime(2026, 4, 6, 13, 0, tzinfo=CHICAGO)
    end = datetime(2026, 4, 6, 14, 0, tzinfo=CHICAGO)

    mock_cal = MagicMock()
    mock_cal.save_event.return_value = None

    with patch(
        "jordan_claw.tools.calendar._get_calendar_async",
        new=AsyncMock(return_value=mock_cal),
    ):
        result = await create_calendar_event(
            "Offsite planning",
            start,
            end,
            location="123 Main St",
            description="Quarterly offsite kickoff",
        )

    assert "Created" in result
    ical_arg = mock_cal.save_event.call_args[0][0]
    assert "123 Main St" in ical_arg
    assert "Quarterly offsite kickoff" in ical_arg


@pytest.mark.asyncio
async def test_caldav_connection_error():
    from jordan_claw.tools.calendar import get_calendar_events

    with patch(
        "jordan_claw.tools.calendar._get_calendar_async",
        new=AsyncMock(side_effect=Exception("Connection refused")),
    ):
        result = await get_calendar_events(
            datetime(2026, 4, 1, tzinfo=CHICAGO),
            datetime(2026, 4, 2, tzinfo=CHICAGO),
        )

    assert "error" in result.lower() or "Error" in result


@pytest.mark.asyncio
async def test_create_event_naive_datetime_treated_as_central():
    """Naive ISO strings from the agent should be treated as Central time."""
    from jordan_claw.tools.calendar import create_calendar_event

    mock_cal = MagicMock()
    mock_cal.save_event.return_value = None

    # Pass naive datetimes (no tzinfo) — the spec says agent sends these
    start = datetime(2026, 4, 2, 14, 0)  # naive
    end = datetime(2026, 4, 2, 15, 0)  # naive

    with patch(
        "jordan_claw.tools.calendar._get_calendar_async",
        new=AsyncMock(return_value=mock_cal),
    ):
        result = await create_calendar_event("Naive event", start, end)

    assert "Created" in result
    assert "14:00" in result
    assert "15:00" in result


@pytest.mark.asyncio
async def test_format_dt_all_day_event():
    """All-day events have date-only DTSTART values; _format_dt should return 'All day'."""
    from jordan_claw.tools.calendar import _format_dt

    all_day = dt_module.date(2026, 4, 5)
    assert _format_dt(all_day) == "All day"


@pytest.mark.asyncio
async def test_create_event_accepts_iso_string():
    """create_calendar_event should accept ISO strings in addition to datetime objects."""
    from jordan_claw.tools.calendar import create_calendar_event

    mock_cal = MagicMock()
    mock_cal.save_event.return_value = None

    with patch(
        "jordan_claw.tools.calendar._get_calendar_async",
        new=AsyncMock(return_value=mock_cal),
    ):
        result = await create_calendar_event(
            "String event", "2026-04-10T09:00:00", "2026-04-10T10:00:00"
        )

    assert "Created" in result
    assert "String event" in result
    assert "09:00" in result


@pytest.mark.asyncio
async def test_tool_without_configure_returns_error():
    """Calling a tool function before configure_calendar returns an error string."""
    from jordan_claw.tools.calendar import get_calendar_events

    # _reset() fixture ensures credentials are None
    result = await get_calendar_events(
        datetime(2026, 4, 1, tzinfo=CHICAGO),
        datetime(2026, 4, 2, tzinfo=CHICAGO),
    )

    assert "error" in result.lower()
    assert "credentials" in result.lower() or "configure" in result.lower()


@pytest.mark.asyncio
async def test_configure_calendar_resets_cache():
    """Calling configure_calendar after a cached connection clears the cache."""
    import jordan_claw.tools.calendar as cal_mod

    # Simulate a populated cache
    fake_calendar = MagicMock()
    cal_mod._calendar_cache = fake_calendar
    cal_mod._username = "user@example.com"
    cal_mod._app_password = "old-password"

    # Reconfigure with new credentials — cache must be cleared
    cal_mod.configure_calendar("new@example.com", "new-password")

    assert cal_mod._calendar_cache is None
    assert cal_mod._username == "new@example.com"
    assert cal_mod._app_password == "new-password"
