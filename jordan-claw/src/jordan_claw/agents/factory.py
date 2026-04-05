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
    memory_context: str = "",
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

    system_prompt = config.system_prompt
    if memory_context:
        system_prompt = memory_context + "\n\n" + system_prompt

    agent = Agent(
        config.model,
        system_prompt=system_prompt,
        tools=tools,
        deps_type=AgentDeps,
    )
    return agent, config.model


CHARS_PER_TOKEN = 4


def db_messages_to_history(
    messages: list[dict],
    max_tokens: int = 4000,
) -> list[ModelRequest | ModelResponse]:
    """Convert DB message rows to Pydantic AI message history format.

    Only converts user and assistant messages. Skips system and tool roles.
    When max_tokens > 0, drops oldest messages first to stay within budget.
    Always preserves at least the most recent user+assistant exchange.
    """
    # First pass: filter to user/assistant and convert
    converted: list[tuple[ModelRequest | ModelResponse, int]] = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        char_count = len(content)

        if role == "user":
            converted.append((ModelRequest(parts=[UserPromptPart(content=content)]), char_count))
        elif role == "assistant":
            converted.append((ModelResponse(parts=[TextPart(content=content)]), char_count))

    if not converted or max_tokens <= 0:
        return [item for item, _ in converted]

    # Second pass: walk newest-to-oldest, accumulate within budget
    max_chars = max_tokens * CHARS_PER_TOKEN
    kept: list[ModelRequest | ModelResponse] = []
    total_chars = 0
    for i in range(len(converted) - 1, -1, -1):
        item, char_count = converted[i]
        if total_chars + char_count > max_chars and len(kept) >= 2:
            break
        kept.append(item)
        total_chars += char_count

    kept.reverse()
    return kept
