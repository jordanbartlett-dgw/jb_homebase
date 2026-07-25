from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from jordan_claw.meds.models import CareProfile, MedicationEntry, MedicationProfile
from jordan_claw.tools.meds import _care_source_hash

ORG_ID = "org-1"


async def _async_return(value):
    return value


def _fake_get_care_document(rows: dict):
    async def _get(db, org_id, doc_type):
        return rows.get(doc_type)

    return _get


@pytest.mark.asyncio
async def test_all_current_returns_sentinel():
    """Nothing changed since generation: no line, no publish (empty content
    is the sentinel dispatch_task/publish_proactive_message honor)."""
    from jordan_claw.proactive.executors import execute_care_docs_check

    care = CareProfile(org_id=ORG_ID, diagnoses=["Long QT syndrome"])
    meds_profile = MedicationProfile(org_id=ORG_ID, timeline_display_name="Jessie")

    emergency_hash = _care_source_hash("emergency", care, meds_profile)
    handoff_hash = _care_source_hash("handoff", care, meds_profile)
    rows = {
        "emergency": {"source_hash": emergency_hash, "generated_at": "2026-07-01T00:00:00+00:00"},
        "handoff": {"source_hash": handoff_hash, "generated_at": "2026-07-01T00:00:00+00:00"},
    }

    with (
        patch("jordan_claw.proactive.executors.get_care_profile", new=AsyncMock(return_value=care)),
        patch(
            "jordan_claw.proactive.executors.get_medication_profile",
            new=AsyncMock(return_value=meds_profile),
        ),
        patch(
            "jordan_claw.proactive.executors.get_care_document",
            new=_fake_get_care_document(rows),
        ),
    ):
        result = await execute_care_docs_check(AsyncMock(), ORG_ID, {}, AsyncMock())

    assert result == ""


@pytest.mark.asyncio
async def test_emergency_stale_from_med_change_names_doc_and_reason():
    """Medications changed since the emergency doc was generated; the handoff
    doesn't depend on medications so it stays current and produces no line."""
    from jordan_claw.proactive.executors import execute_care_docs_check

    old_meds = MedicationProfile(org_id=ORG_ID, timeline_display_name="Jessie")
    new_meds = MedicationProfile(
        org_id=ORG_ID,
        timeline_display_name="Jessie",
        medications=[MedicationEntry(name="Levetiracetam", dose="250mg")],
    )
    care = CareProfile(org_id=ORG_ID, diagnoses=["Long QT syndrome"])

    stored_emergency_hash = _care_source_hash("emergency", care, old_meds)
    stored_handoff_hash = _care_source_hash("handoff", care, old_meds)
    rows = {
        "emergency": {
            "source_hash": stored_emergency_hash,
            "generated_at": "2026-07-01T00:00:00+00:00",
        },
        "handoff": {
            "source_hash": stored_handoff_hash,
            "generated_at": "2026-07-01T00:00:00+00:00",
        },
    }

    with (
        patch("jordan_claw.proactive.executors.get_care_profile", new=AsyncMock(return_value=care)),
        patch(
            "jordan_claw.proactive.executors.get_medication_profile",
            new=AsyncMock(return_value=new_meds),
        ),
        patch(
            "jordan_claw.proactive.executors.get_care_document",
            new=_fake_get_care_document(rows),
        ),
    ):
        result = await execute_care_docs_check(AsyncMock(), ORG_ID, {}, AsyncMock())

    assert result != ""
    lines = result.splitlines()
    assert len(lines) == 1
    assert "emergency one-pager" in lines[0]
    assert "Jessie's" in lines[0]
    assert "medications changed" in lines[0]
    assert "Ask med-check to regenerate it." in lines[0]
    assert "caregiver handoff" not in result


@pytest.mark.asyncio
async def test_both_never_generated_both_lines_present():
    from jordan_claw.proactive.executors import execute_care_docs_check

    care = CareProfile(org_id=ORG_ID, diagnoses=["Long QT syndrome"])
    meds_profile = MedicationProfile(org_id=ORG_ID, timeline_display_name="Jessie")
    rows: dict = {"emergency": None, "handoff": None}

    with (
        patch("jordan_claw.proactive.executors.get_care_profile", new=AsyncMock(return_value=care)),
        patch(
            "jordan_claw.proactive.executors.get_medication_profile",
            new=AsyncMock(return_value=meds_profile),
        ),
        patch(
            "jordan_claw.proactive.executors.get_care_document",
            new=_fake_get_care_document(rows),
        ),
    ):
        result = await execute_care_docs_check(AsyncMock(), ORG_ID, {}, AsyncMock())

    lines = result.splitlines()
    assert len(lines) == 2
    assert any(
        "emergency one-pager" in line and "has not been generated yet" in line for line in lines
    )
    assert any(
        "caregiver handoff" in line and "has not been generated yet" in line for line in lines
    )
    assert all("Jessie's" in line for line in lines)


@pytest.mark.asyncio
async def test_display_name_fallback_when_unset():
    """No timeline_display_name on the medication profile: message falls back
    to naming the care docs generically instead of a possessive with no name."""
    from jordan_claw.proactive.executors import execute_care_docs_check

    care = CareProfile(org_id=ORG_ID, diagnoses=["Long QT syndrome"])
    meds_profile = MedicationProfile(org_id=ORG_ID)  # no timeline_display_name
    rows: dict = {"emergency": None, "handoff": None}

    with (
        patch("jordan_claw.proactive.executors.get_care_profile", new=AsyncMock(return_value=care)),
        patch(
            "jordan_claw.proactive.executors.get_medication_profile",
            new=AsyncMock(return_value=meds_profile),
        ),
        patch(
            "jordan_claw.proactive.executors.get_care_document",
            new=_fake_get_care_document(rows),
        ),
    ):
        result = await execute_care_docs_check(AsyncMock(), ORG_ID, {}, AsyncMock())

    lines = result.splitlines()
    assert len(lines) == 2
    assert all("the care docs" in line.lower() for line in lines)
