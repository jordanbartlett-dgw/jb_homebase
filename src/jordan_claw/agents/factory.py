from __future__ import annotations

from pydantic_ai import Agent, ModelRequest, ModelResponse, TextPart, ToolReturnPart, UserPromptPart
from pydantic_ai.capabilities import ProcessHistory
from supabase._async.client import AsyncClient

from jordan_claw.agents.capabilities import resolve_capabilities
from jordan_claw.agents.deps import AgentDeps
from jordan_claw.db.agents import AgentConfig, get_agent_config


def create_agent(
    config: AgentConfig,
    memory_context: str = "",
) -> tuple[Agent[AgentDeps], str]:
    """Construct a Pydantic AI agent from an already-fetched config.

    Returns (agent, model_name) so callers can log/store the model
    without reaching into Pydantic AI internals.
    """
    system_prompt = config.system_prompt
    if memory_context:
        system_prompt = memory_context + "\n\n" + system_prompt

    agent = Agent(
        config.model,
        instructions=system_prompt,
        capabilities=[
            *resolve_capabilities(config.capabilities),
            ProcessHistory(trim_history_processor),
        ],
        deps_type=AgentDeps,
    )
    return agent, config.model


async def build_agent(
    db: AsyncClient,
    org_id: str,
    agent_slug: str,
    memory_context: str = "",
) -> tuple[Agent[AgentDeps], str]:
    """Build a Pydantic AI agent from DB config using toolsets."""
    config = await get_agent_config(db, org_id, agent_slug)
    return create_agent(config, memory_context=memory_context)


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
    # Never strip to empty — pydantic-ai requires non-empty processed history.
    while len(kept) > 1:
        first = kept[0]
        if (
            isinstance(first, ModelResponse)
            or isinstance(first, ModelRequest)
            and any(isinstance(p, ToolReturnPart) for p in first.parts)
        ):
            kept.pop(0)
        else:
            break

    return kept


def db_messages_to_history(messages: list[dict]) -> list[ModelRequest | ModelResponse]:
    """Convert DB message rows to Pydantic AI message history format.

    Only converts user and assistant messages. Skips system and tool roles.
    Trimming happens in trim_history_processor, wired as a ProcessHistory
    capability on every agent.
    """
    converted: list[ModelRequest | ModelResponse] = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if role == "user":
            converted.append(ModelRequest(parts=[UserPromptPart(content=content)]))
        elif role == "assistant":
            converted.append(ModelResponse(parts=[TextPart(content=content)]))

    return converted
