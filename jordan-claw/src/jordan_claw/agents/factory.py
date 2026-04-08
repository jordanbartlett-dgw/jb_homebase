from __future__ import annotations

import structlog
from pydantic_ai import Agent, ModelRequest, ModelResponse, TextPart, ToolReturnPart, UserPromptPart
from pydantic_ai.tools import RunContext, ToolDefinition
from supabase._async.client import AsyncClient

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.db.agents import get_agent_config
from jordan_claw.tools import BASE_TOOLSET

log = structlog.get_logger()


def _make_tool_filter(allowed_tools: list[str]):
    """Return a filter function for FilteredToolset that allows only named tools."""
    allowed = set(allowed_tools)

    def filter_func(ctx: RunContext[AgentDeps], tool_def: ToolDefinition) -> bool:
        return tool_def.name in allowed

    return filter_func


async def build_agent(
    db: AsyncClient,
    org_id: str,
    agent_slug: str,
    memory_context: str = "",
) -> tuple[Agent[AgentDeps], str]:
    """Build a Pydantic AI agent from DB config using toolsets.

    Returns (agent, model_name) so callers can log/store the model
    without reaching into Pydantic AI internals.
    """
    config = await get_agent_config(db, org_id, agent_slug)

    # Log any tools in config that don't exist in BASE_TOOLSET
    for name in config.tools:
        if name not in BASE_TOOLSET.tools:
            log.warning("unknown_tool_skipped", tool_name=name, agent_slug=agent_slug)

    filtered = BASE_TOOLSET.filtered(_make_tool_filter(config.tools))

    system_prompt = config.system_prompt
    if memory_context:
        system_prompt = memory_context + "\n\n" + system_prompt

    agent = Agent(
        config.model,
        instructions=system_prompt,
        toolsets=[filtered],
        history_processors=[trim_history_processor],
        deps_type=AgentDeps,
    )
    return agent, config.model


CHARS_PER_TOKEN = 4


def trim_history_processor(
    messages: list[ModelRequest | ModelResponse],
    max_tokens: int = 4000,
) -> list[ModelRequest | ModelResponse]:
    """History processor that trims oldest messages to stay within token budget.

    Always preserves at least the most recent user+assistant exchange.
    Ensures history never starts with an assistant message.
    """
    if not messages or max_tokens <= 0:
        return messages

    max_chars = max_tokens * CHARS_PER_TOKEN
    kept: list[ModelRequest | ModelResponse] = []
    total_chars = 0
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        char_count = sum(len(p.content) for p in msg.parts if hasattr(p, "content"))
        if total_chars + char_count > max_chars and len(kept) >= 2:
            break
        kept.append(msg)
        total_chars += char_count

    kept.reverse()

    # Strip leading ModelResponse (orphaned assistant) and ModelRequest
    # containing ToolReturnPart (orphaned tool_result without tool_use).
    while kept:
        first = kept[0]
        if isinstance(first, ModelResponse):
            kept.pop(0)
        elif isinstance(first, ModelRequest) and any(
            isinstance(p, ToolReturnPart) for p in first.parts
        ):
            kept.pop(0)
        else:
            break

    return kept


def db_messages_to_history(
    messages: list[dict],
    max_tokens: int = 4000,
) -> list[ModelRequest | ModelResponse]:
    """Convert DB message rows to Pydantic AI message history format.

    Only converts user and assistant messages. Skips system and tool roles.
    When max_tokens > 0, drops oldest messages first to stay within budget.
    Always preserves at least the most recent user+assistant exchange.
    """
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

    while kept and isinstance(kept[0], ModelResponse):
        kept.pop(0)

    return kept
