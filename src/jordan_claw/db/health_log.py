from __future__ import annotations

from supabase._async.client import AsyncClient

from jordan_claw.meds.models import HealthEvent


async def insert_health_event(
    client: AsyncClient,
    org_id: str,
    *,
    event_date: str,
    category: str,
    title: str,
    details: dict | None = None,
    notes: str | None = None,
    severity: str | None = None,
) -> dict:
    data: dict = {
        "org_id": org_id,
        "event_date": event_date,
        "category": category,
        "title": title,
        "details": details or {},
    }
    if notes is not None:
        data["notes"] = notes
    if severity is not None:
        data["severity"] = severity
    result = await client.table("health_events").insert(data).execute()
    return result.data[0]


async def get_events_for_date(
    client: AsyncClient,
    org_id: str,
    event_date: str,
) -> list[HealthEvent]:
    result = (
        await client.table("health_events")
        .select("*")
        .eq("org_id", org_id)
        .eq("event_date", event_date)
        .order("logged_at", desc=False)
        .execute()
    )
    return [HealthEvent.model_validate(row) for row in result.data]


async def get_latest_health_event(client: AsyncClient, org_id: str) -> HealthEvent | None:
    """Most recently logged event (by logged_at, not event_date)."""
    result = (
        await client.table("health_events")
        .select("*")
        .eq("org_id", org_id)
        .order("logged_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return HealthEvent.model_validate(result.data[0])


async def update_health_event(
    client: AsyncClient,
    org_id: str,
    event_id: str,
    *,
    details: dict | None = None,
    notes: str | None = None,
    category: str | None = None,
    event_date: str | None = None,
    severity: str | None = None,
) -> dict:
    data: dict = {}
    if details is not None:
        data["details"] = details
    if notes is not None:
        data["notes"] = notes
    if category is not None:
        data["category"] = category
    if event_date is not None:
        data["event_date"] = event_date
    if severity is not None:
        data["severity"] = severity
    result = (
        await client.table("health_events")
        .update(data)
        .eq("id", event_id)
        .eq("org_id", org_id)
        .execute()
    )
    return result.data[0] if result.data else {}


async def get_health_events_range(
    client: AsyncClient,
    org_id: str,
    start_date: str,
    end_date: str,
    category: str | None = None,
) -> list[HealthEvent]:
    query = (
        client.table("health_events")
        .select("*")
        .eq("org_id", org_id)
        .gte("event_date", start_date)
        .lte("event_date", end_date)
    )
    if category is not None:
        query = query.eq("category", category)
    result = await query.order("event_date", desc=False).execute()
    return [HealthEvent.model_validate(row) for row in result.data]


async def get_last_appointment_date(client: AsyncClient, org_id: str) -> str | None:
    """Newest event_date among category='appointment' events, else None."""
    result = (
        await client.table("health_events")
        .select("*")
        .eq("org_id", org_id)
        .eq("category", "appointment")
        .order("event_date", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return result.data[0]["event_date"]
