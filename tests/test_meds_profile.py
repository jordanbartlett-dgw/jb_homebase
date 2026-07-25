from __future__ import annotations

import pytest

from jordan_claw.meds.models import MedicationEntry, MedicationProfile


def test_missing_fields_reports_empty_sections():
    profile = MedicationProfile(org_id="org-1")
    missing = profile.missing_fields()
    assert "medications" in missing
    assert "allergies" in missing
    assert "notes" in missing


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
