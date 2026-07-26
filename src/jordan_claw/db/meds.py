from __future__ import annotations

from datetime import UTC, datetime

from supabase._async.client import AsyncClient

from jordan_claw.meds.models import MedicationProfile

PROFILE_FIELDS = (
    "medications",
    "allergies",
    "notes",
    "timeline_display_name",
    "date_of_birth",
)


async def get_medication_profile(client: AsyncClient, org_id: str) -> MedicationProfile | None:
    """Load the medication profile for an org, or None if never filled."""
    result = (
        await client.table("medication_profiles")
        .select("*")
        .eq("org_id", org_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return MedicationProfile.model_validate(result.data[0])


async def upsert_medication_profile(client: AsyncClient, org_id: str, **fields) -> None:
    """Partial upsert: only provided, non-None profile fields are written."""
    data = {k: v for k, v in fields.items() if k in PROFILE_FIELDS and v is not None}
    data["org_id"] = org_id
    data["updated_at"] = datetime.now(UTC).isoformat()
    await client.table("medication_profiles").upsert(data, on_conflict="org_id").execute()
