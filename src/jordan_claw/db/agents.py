from __future__ import annotations

from pydantic import BaseModel
from supabase._async.client import AsyncClient


class AgentConfig(BaseModel):
    """Typed representation of an agent row from the agents table."""

    id: str
    org_id: str
    name: str
    slug: str
    system_prompt: str
    model: str
    capabilities: list[str] = []
    is_active: bool


async def get_org_default_model(client: AsyncClient, org_id: str) -> str | None:
    """Org-level default model (organizations.default_model, migration 019)."""
    result = (
        await client.table("organizations")
        .select("default_model")
        .eq("id", org_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return result.data[0].get("default_model")


def resolve_model(agent_model: str | None, org_default: str | None) -> str:
    """Per-agent override wins; NULL on the agent row means the org default."""
    model = agent_model or org_default
    if not model:
        raise ValueError("No model configured: agent model and org default_model are both unset")
    return model


async def get_agent_config(client: AsyncClient, org_id: str, slug: str) -> AgentConfig:
    """Fetch a single active agent config by org_id and slug.

    A NULL model column resolves to the org's default_model, so AgentConfig
    always carries a concrete provider-prefixed model string.
    """
    result = (
        await client.table("agents")
        .select("id, org_id, name, slug, system_prompt, model, capabilities, is_active")
        .eq("org_id", org_id)
        .eq("slug", slug)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )

    if not result.data:
        raise ValueError(f"Agent not found: org_id={org_id}, slug={slug}")

    row = result.data[0]
    if not row.get("model"):
        row["model"] = resolve_model(None, await get_org_default_model(client, org_id))
    return AgentConfig.model_validate(row)
