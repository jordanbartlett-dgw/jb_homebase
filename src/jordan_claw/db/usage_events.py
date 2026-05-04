from __future__ import annotations

from decimal import Decimal

from supabase._async.client import AsyncClient

from jordan_claw.analytics.types import RunKind


async def save_usage_event(
    client: AsyncClient,
    *,
    org_id: str,
    agent_slug: str,
    conversation_id: str | None,
    channel: str,
    run_kind: RunKind,
    schedule_name: str | None,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: Decimal | None,
    duration_ms: int,
    tool_call_count: int,
    success: bool,
    error_type: str | None,
    error_severity: str | None,
    metadata: dict | None = None,
) -> None:
    """Insert one row into usage_events. None-valued optional fields are dropped."""
    data: dict = {
        "org_id": org_id,
        "agent_slug": agent_slug,
        "channel": channel,
        "run_kind": run_kind.value if isinstance(run_kind, RunKind) else run_kind,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "duration_ms": duration_ms,
        "tool_call_count": tool_call_count,
        "success": success,
    }
    if conversation_id is not None:
        data["conversation_id"] = conversation_id
    if schedule_name is not None:
        data["schedule_name"] = schedule_name
    if cost_usd is not None:
        data["cost_usd"] = float(cost_usd)
    if error_type is not None:
        data["error_type"] = error_type
    if error_severity is not None:
        data["error_severity"] = error_severity
    if metadata is not None:
        data["metadata"] = metadata

    await client.table("usage_events").insert(data).execute()


async def most_recent_agent(
    client: AsyncClient,
    *,
    org_id: str,
    channel: str,
) -> str | None:
    """Return the agent_slug of the most recent user_message run on this channel.

    No time cutoff — used by the /feedback command (PR4) to attribute a
    rating to the agent the user was most recently talking to.
    """
    result = (
        await client.table("usage_events")
        .select("agent_slug")
        .eq("org_id", org_id)
        .eq("channel", channel)
        .eq("run_kind", RunKind.USER_MESSAGE.value)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return result.data[0]["agent_slug"]
