from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from jordan_claw.db.meds import upsert_medication_profile
from jordan_claw.meds.models import MedicationEntry, MedicationProfile

ORG_ID = "org-1"


def _mock_db(select_data=None):
    """Mock Supabase async client with chained query builder (same pattern as test_db_workout)."""
    mock_result = MagicMock(data=select_data or [])

    mock_query = MagicMock()
    mock_query.execute = AsyncMock(return_value=mock_result)
    mock_query.limit.return_value = mock_query
    mock_query.eq.return_value = mock_query
    mock_query.select.return_value = mock_query
    mock_query.upsert.return_value = mock_query

    mock_db = MagicMock()
    mock_db.table.return_value = mock_query
    return mock_db, mock_query


def test_missing_fields_reports_empty_sections():
    profile = MedicationProfile(org_id="org-1")
    missing = profile.missing_fields()
    assert "medications" in missing
    assert "allergies" in missing
    assert "notes" in missing


def test_missing_fields_ignores_timeline_display_name():
    """timeline_display_name is optional display config, not a core field —
    it must never appear in missing_fields(), whether set or unset."""
    profile = MedicationProfile(org_id="org-1")
    assert "timeline_display_name" not in profile.missing_fields()

    profile_with_name = MedicationProfile(
        org_id="org-1",
        medications=[
            MedicationEntry(name="ondansetron", rxcui="26225", dose="4 mg PRN", prescriber="Dr. A")
        ],
        allergies="none known",
        notes="cardiology: Dr. B, baseline QTc 470ms",
        timeline_display_name=None,
    )
    assert profile_with_name.missing_fields() == []


def test_missing_fields_empty_when_populated():
    profile = MedicationProfile(
        org_id="org-1",
        medications=[
            MedicationEntry(name="ondansetron", rxcui="26225", dose="4 mg PRN", prescriber="Dr. A")
        ],
        allergies="none known",
        notes="cardiology: Dr. B, baseline QTc 470ms",
    )
    assert profile.missing_fields() == []


@pytest.mark.asyncio
async def test_partial_save_only_writes_provided_fields(monkeypatch):
    """save_medication_profile(allergies=...) must not clobber medications.
    Assert the upsert payload contains only org_id, allergies, updated_at."""
    captured: dict = {}

    async def fake_upsert(client, org_id, **fields):
        captured.update({k: v for k, v in fields.items() if v is not None})

    from jordan_claw.tools import meds as meds_tools

    monkeypatch.setattr(meds_tools, "upsert_medication_profile", fake_upsert)

    class FakeCtx:
        class deps:  # noqa: N801 — mirrors ctx.deps attribute access, not a real class
            org_id = "org-1"
            supabase_client = None

    out = await meds_tools.save_medication_profile(FakeCtx(), allergies="penicillin")
    assert "saved" in out.lower()
    assert captured == {"allergies": "penicillin"}


@pytest.mark.asyncio
async def test_upsert_medication_profile_only_sends_provided_fields():
    """Direct unit test of the DB-layer payload construction (PROFILE_FIELDS
    filter + org_id/updated_at injection) — the code that actually guarantees
    an allergies-only save doesn't clobber medications. The tools-layer test
    above only proves kwarg forwarding, not this."""
    db, query = _mock_db()
    await upsert_medication_profile(
        db, ORG_ID, medications=None, allergies="penicillin", notes=None
    )
    sent = query.upsert.call_args[0][0]
    assert set(sent.keys()) == {"org_id", "allergies", "updated_at"}
    assert sent["org_id"] == ORG_ID
    assert sent["allergies"] == "penicillin"
    assert "updated_at" in sent
    assert query.upsert.call_args.kwargs["on_conflict"] == "org_id"
    db.table.assert_called_with("medication_profiles")
