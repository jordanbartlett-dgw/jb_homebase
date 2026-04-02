from __future__ import annotations

import structlog
from pydantic import BaseModel
from supabase._async.client import AsyncClient

log = structlog.get_logger()


class AgentConfig(BaseModel):
    """Typed representation of an agent row from the agents table."""

    id: str
    org_id: str
    name: str
    slug: str
    system_prompt: str
    model: str
    tools: list[str]
    is_active: bool


async def get_agent_config(
    client: AsyncClient, org_id: str, slug: str
) -> AgentConfig:
    """Fetch a single active agent config by org_id and slug."""
    result = (
        await client.table("agents")
        .select("id, org_id, name, slug, system_prompt, model, tools, is_active")
        .eq("org_id", org_id)
        .eq("slug", slug)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )

    if not result.data:
        raise ValueError(f"Agent not found: org_id={org_id}, slug={slug}")

    return AgentConfig.model_validate(result.data[0])
