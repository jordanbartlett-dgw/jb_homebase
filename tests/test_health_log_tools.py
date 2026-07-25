from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from jordan_claw.meds.models import HealthEvent
from jordan_claw.tools.meds import (
    amend_last_health_event,
    get_health_events,
    get_last_visit_date,
    log_health_event,
)


def _make_ctx(org_id: str = "org-001"):
    ctx = MagicMock()
    ctx.deps.org_id = org_id
    ctx.deps.supabase_client = MagicMock()
    return ctx


def _existing_event(category: str = "seizure", **overrides) -> HealthEvent:
    data = {
        "id": "e-existing",
        "org_id": "org-001",
        "event_date": "2026-07-25",
        "category": category,
        "title": "Brief tonic-clonic",
        "details": {"duration_sec": 45},
        "notes": "recovered quickly",
        "severity": "moderate",
        "logged_at": "2026-07-25T18:00:00+00:00",
    }
    data.update(overrides)
    return HealthEvent(**data)


@pytest.mark.asyncio
async def test_log_health_event_inserts_when_no_clash():
    ctx = _make_ctx()
    with (
        patch("jordan_claw.tools.meds.get_events_for_date", return_value=[]),
        patch(
            "jordan_claw.tools.meds.insert_health_event", return_value={"id": "e1"}
        ) as mock_insert,
    ):
        result = await log_health_event(
            ctx, event_date="2026-07-25", category="seizure", title="Brief tonic-clonic"
        )
    mock_insert.assert_called_once()
    assert mock_insert.call_args.kwargs["event_date"] == "2026-07-25"
    assert mock_insert.call_args.kwargs["category"] == "seizure"
    assert mock_insert.call_args.kwargs["title"] == "Brief tonic-clonic"
    assert "logged" in result.lower()


@pytest.mark.asyncio
async def test_log_health_event_refuses_same_day_same_category():
    """Follow-up detail about an already-logged event must not create a second row."""
    ctx = _make_ctx()
    with (
        patch(
            "jordan_claw.tools.meds.get_events_for_date",
            return_value=[_existing_event("seizure")],
        ),
        patch("jordan_claw.tools.meds.insert_health_event") as mock_insert,
    ):
        result = await log_health_event(
            ctx, event_date="2026-07-25", category="seizure", title="Second seizure"
        )
    mock_insert.assert_not_called()
    assert "amend_last_health_event" in result
    assert "allow_duplicate" in result
    assert "Brief tonic-clonic" in result  # existing event named so the model can decide


@pytest.mark.asyncio
async def test_log_health_event_allows_duplicate_when_flagged():
    """Repeat episodes on the same day (e.g. a second seizure) are real and expected."""
    ctx = _make_ctx()
    with (
        patch(
            "jordan_claw.tools.meds.get_events_for_date",
            return_value=[_existing_event("seizure")],
        ),
        patch(
            "jordan_claw.tools.meds.insert_health_event", return_value={"id": "e2"}
        ) as mock_insert,
    ):
        result = await log_health_event(
            ctx,
            event_date="2026-07-25",
            category="seizure",
            title="Second seizure",
            allow_duplicate=True,
        )
    mock_insert.assert_called_once()
    assert "logged" in result.lower()


@pytest.mark.asyncio
async def test_log_health_event_allows_different_category_same_day():
    ctx = _make_ctx()
    with (
        patch(
            "jordan_claw.tools.meds.get_events_for_date",
            return_value=[_existing_event("seizure")],
        ),
        patch(
            "jordan_claw.tools.meds.insert_health_event", return_value={"id": "e2"}
        ) as mock_insert,
    ):
        result = await log_health_event(
            ctx, event_date="2026-07-25", category="gi", title="Reflux episode"
        )
    mock_insert.assert_called_once()
    assert "logged" in result.lower()


@pytest.mark.asyncio
async def test_amend_merges_details_and_appends_notes():
    ctx = _make_ctx()
    with (
        patch(
            "jordan_claw.tools.meds.get_latest_health_event",
            return_value=_existing_event(),
        ),
        patch("jordan_claw.tools.meds.update_health_event", return_value={}) as mock_update,
    ):
        result = await amend_last_health_event(
            ctx, details={"recovery_min": 10}, notes="slept after"
        )
    kwargs = mock_update.call_args.kwargs
    assert kwargs["details"] == {"duration_sec": 45, "recovery_min": 10}
    assert kwargs["notes"] == "recovered quickly\nslept after"
    assert "updated" in result.lower() or "amended" in result.lower()


@pytest.mark.asyncio
async def test_amend_replaces_category_event_date_severity():
    ctx = _make_ctx()
    with (
        patch(
            "jordan_claw.tools.meds.get_latest_health_event",
            return_value=_existing_event(),
        ),
        patch("jordan_claw.tools.meds.update_health_event", return_value={}) as mock_update,
    ):
        await amend_last_health_event(
            ctx, category="illness", event_date="2026-07-24", severity="mild"
        )
    kwargs = mock_update.call_args.kwargs
    assert kwargs["category"] == "illness"
    assert kwargs["event_date"] == "2026-07-24"
    assert kwargs["severity"] == "mild"


@pytest.mark.asyncio
async def test_amend_without_existing_event_points_to_log():
    ctx = _make_ctx()
    with patch("jordan_claw.tools.meds.get_latest_health_event", return_value=None):
        result = await amend_last_health_event(ctx, notes="follow up")
    assert "No health event logged yet" in result
    assert "log_health_event" in result


@pytest.mark.asyncio
async def test_get_health_events_formats_with_details_and_notes():
    ctx = _make_ctx()
    with patch("jordan_claw.tools.meds.get_health_events_range", return_value=[_existing_event()]):
        result = await get_health_events(ctx, "2026-07-01", "2026-07-31")
    assert "- [2026-07-25] seizure: Brief tonic-clonic" in result
    assert "duration_sec=45" in result
    assert "recovered quickly" in result
    assert "days later" not in result  # logged same day as it happened


@pytest.mark.asyncio
async def test_get_health_events_adds_late_logged_marker():
    late_event = _existing_event(logged_at="2026-07-28T10:00:00+00:00")  # event_date 2026-07-25
    ctx = _make_ctx()
    with patch("jordan_claw.tools.meds.get_health_events_range", return_value=[late_event]):
        result = await get_health_events(ctx, "2026-07-01", "2026-07-31")
    assert "(logged 3 days later)" in result


@pytest.mark.asyncio
async def test_get_health_events_no_marker_for_next_day_logging():
    """Exactly one day later is not 'late' — the marker requires > 1 day."""
    next_day_event = _existing_event(logged_at="2026-07-26T10:00:00+00:00")
    ctx = _make_ctx()
    with patch("jordan_claw.tools.meds.get_health_events_range", return_value=[next_day_event]):
        result = await get_health_events(ctx, "2026-07-01", "2026-07-31")
    assert "days later" not in result


@pytest.mark.asyncio
async def test_get_health_events_empty_range():
    ctx = _make_ctx()
    with patch("jordan_claw.tools.meds.get_health_events_range", return_value=[]):
        result = await get_health_events(ctx, "2026-07-01", "2026-07-31")
    assert result == "No health events logged in that range."


@pytest.mark.asyncio
async def test_get_health_events_passes_category_filter():
    ctx = _make_ctx()
    with patch("jordan_claw.tools.meds.get_health_events_range", return_value=[]) as mock_range:
        await get_health_events(ctx, "2026-07-01", "2026-07-31", category="seizure")
    mock_range.assert_called_once_with(
        ctx.deps.supabase_client, "org-001", "2026-07-01", "2026-07-31", category="seizure"
    )


@pytest.mark.asyncio
async def test_get_last_visit_date_returns_message_when_none():
    ctx = _make_ctx()
    with patch("jordan_claw.tools.meds.get_last_appointment_date", return_value=None):
        result = await get_last_visit_date(ctx)
    assert "no appointment" in result.lower()


@pytest.mark.asyncio
async def test_get_last_visit_date_returns_date():
    ctx = _make_ctx()
    with patch("jordan_claw.tools.meds.get_last_appointment_date", return_value="2026-06-01"):
        result = await get_last_visit_date(ctx)
    assert "2026-06-01" in result
