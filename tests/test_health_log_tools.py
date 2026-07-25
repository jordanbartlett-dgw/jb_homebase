from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

import pytest

from jordan_claw.meds.models import HealthEvent, MedicationEntry, MedicationProfile
from jordan_claw.tools.meds import (
    amend_last_health_event,
    get_health_events,
    get_last_visit_date,
    log_health_event,
    save_medication_profile,
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


@pytest.mark.asyncio
async def test_save_medication_profile_logs_change_event_with_full_diff():
    """Added, removed, and changed-dose meds in one save produce one event
    with all three diff keys populated."""
    ctx = _make_ctx()
    old_profile = MedicationProfile(
        org_id="org-001",
        medications=[
            MedicationEntry(name="lamotrigine", dose="25 mg"),
            MedicationEntry(name="ondansetron", dose="4 mg PRN"),
        ],
    )
    new_meds = [
        MedicationEntry(name="lamotrigine", dose="50 mg"),  # dose changed
        MedicationEntry(name="melatonin", dose="3 mg"),  # added
        # ondansetron dropped -> removed
    ]
    with (
        patch("jordan_claw.tools.meds.get_medication_profile", return_value=old_profile),
        patch("jordan_claw.tools.meds.upsert_medication_profile", return_value=None),
        patch(
            "jordan_claw.tools.meds.insert_health_event", return_value={"id": "e1"}
        ) as mock_insert,
    ):
        result = await save_medication_profile(ctx, medications=new_meds)

    mock_insert.assert_called_once()
    kwargs = mock_insert.call_args.kwargs
    assert kwargs["category"] == "medication_change"
    assert kwargs["title"] == "Medication change"
    assert kwargs["details"] == {
        "added": ["melatonin"],
        "removed": ["ondansetron"],
        "changed": [{"name": "lamotrigine", "dose_from": "25 mg", "dose_to": "50 mg"}],
    }
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", kwargs["event_date"])
    assert "medication_change" in result


@pytest.mark.asyncio
async def test_save_medication_profile_no_event_when_med_list_unchanged():
    """Re-saving the identical medications list must not log a duplicate event."""
    ctx = _make_ctx()
    profile = MedicationProfile(
        org_id="org-001",
        medications=[MedicationEntry(name="lamotrigine", dose="25 mg")],
    )
    same_meds = [MedicationEntry(name="lamotrigine", dose="25 mg")]
    with (
        patch("jordan_claw.tools.meds.get_medication_profile", return_value=profile),
        patch("jordan_claw.tools.meds.upsert_medication_profile", return_value=None),
        patch("jordan_claw.tools.meds.insert_health_event") as mock_insert,
    ):
        result = await save_medication_profile(ctx, medications=same_meds)
    mock_insert.assert_not_called()
    assert result == "Medication profile saved."


@pytest.mark.asyncio
async def test_save_medication_profile_allergies_only_no_event():
    """A field-only save (no medications arg) never touches the med diff at all."""
    ctx = _make_ctx()
    with (
        patch("jordan_claw.tools.meds.get_medication_profile") as mock_get,
        patch("jordan_claw.tools.meds.upsert_medication_profile", return_value=None),
        patch("jordan_claw.tools.meds.insert_health_event") as mock_insert,
    ):
        result = await save_medication_profile(ctx, allergies="penicillin")
    mock_get.assert_not_called()
    mock_insert.assert_not_called()
    assert result == "Medication profile saved."


@pytest.mark.asyncio
async def test_save_medication_profile_no_prior_profile_all_added():
    """First-ever med save (no existing profile row) logs every med as added."""
    ctx = _make_ctx()
    new_meds = [
        MedicationEntry(name="lamotrigine", dose="25 mg"),
        MedicationEntry(name="melatonin", dose="3 mg"),
    ]
    with (
        patch("jordan_claw.tools.meds.get_medication_profile", return_value=None),
        patch("jordan_claw.tools.meds.upsert_medication_profile", return_value=None),
        patch(
            "jordan_claw.tools.meds.insert_health_event", return_value={"id": "e1"}
        ) as mock_insert,
    ):
        await save_medication_profile(ctx, medications=new_meds)
    mock_insert.assert_called_once()
    kwargs = mock_insert.call_args.kwargs
    assert kwargs["details"] == {"added": ["lamotrigine", "melatonin"]}
    assert "removed" not in kwargs["details"]
    assert "changed" not in kwargs["details"]


@pytest.mark.asyncio
async def test_save_medication_profile_passes_timeline_display_name():
    """timeline_display_name is forwarded to the DB-layer upsert."""
    ctx = _make_ctx()
    with patch(
        "jordan_claw.tools.meds.upsert_medication_profile", return_value=None
    ) as mock_upsert:
        await save_medication_profile(ctx, timeline_display_name="Grandma J.")
    kwargs = mock_upsert.call_args.kwargs
    assert kwargs["timeline_display_name"] == "Grandma J."
