from __future__ import annotations

import structlog
from pydantic_ai import Agent, ModelRequest, ModelResponse, TextPart, UserPromptPart
from supabase._async.client import AsyncClient

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.db.agents import get_agent_config
from jordan_claw.tools import TOOL_REGISTRY

log = structlog.get_logger()


async def build_agent(
    db: AsyncClient,
    org_id: str,
    agent_slug: str,
) -> tuple[Agent[AgentDeps], str]:
    """Build a Pydantic AI agent from DB config and the tool registry.

    Returns (agent, model_name) so callers can log/store the model
    without reaching into Pydantic AI internals.
    """
    config = await get_agent_config(db, org_id, agent_slug)

    tools = []
    for name in config.tools:
        if name in TOOL_REGISTRY:
            tools.append(TOOL_REGISTRY[name])
        else:
            log.warning("unknown_tool_skipped", tool_name=name, agent_slug=agent_slug)

    agent = Agent(
        config.model,
        system_prompt=config.system_prompt,
        tools=tools,
        deps_type=AgentDeps,
    )
    return agent, config.model


def db_messages_to_history(messages: list[dict]) -> list[ModelRequest | ModelResponse]:
    """Convert DB message rows to Pydantic AI message history format.

    Only converts user and assistant messages. Skips system and tool roles.
    """
    history: list[ModelRequest | ModelResponse] = []

    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if role == "user":
            history.append(ModelRequest(parts=[UserPromptPart(content=content)]))
        elif role == "assistant":
            history.append(ModelResponse(parts=[TextPart(content=content)]))

    return history
