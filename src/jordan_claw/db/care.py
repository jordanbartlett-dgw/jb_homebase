from __future__ import annotations

from datetime import UTC, datetime

from supabase._async.client import AsyncClient

from jordan_claw.meds.models import CareProfile

CARE_PROFILE_FIELDS = (
    "diagnoses",
    "critical_flags",
    "seizure_plan",
    "baselines",
    "communication",
    "routines",
    "escalation",
    "contacts",
)


async def get_care_profile(client: AsyncClient, org_id: str) -> CareProfile | None:
    """Load the care profile for an org, or None if never filled."""
    result = await client.table("care_profiles").select("*").eq("org_id", org_id).limit(1).execute()
    if not result.data:
        return None
    return CareProfile.model_validate(result.data[0])


async def upsert_care_profile(client: AsyncClient, org_id: str, **fields) -> None:
    """Partial upsert: only provided, non-None profile fields are written."""
    data = {k: v for k, v in fields.items() if k in CARE_PROFILE_FIELDS and v is not None}
    data["org_id"] = org_id
    data["updated_at"] = datetime.now(UTC).isoformat()
    await client.table("care_profiles").upsert(data, on_conflict="org_id").execute()


async def get_care_document(client: AsyncClient, org_id: str, doc_type: str) -> dict | None:
    """Load the latest generated document of doc_type for an org, or None if never generated."""
    result = (
        await client.table("care_documents")
        .select("*")
        .eq("org_id", org_id)
        .eq("doc_type", doc_type)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return result.data[0]


async def upsert_care_document(
    client: AsyncClient,
    org_id: str,
    *,
    doc_type: str,
    source_hash: str,
    note_title: str,
) -> None:
    """Record (or replace) the generated-document fingerprint for org_id + doc_type."""
    data = {
        "org_id": org_id,
        "doc_type": doc_type,
        "source_hash": source_hash,
        "note_title": note_title,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    await client.table("care_documents").upsert(data, on_conflict="org_id,doc_type").execute()
