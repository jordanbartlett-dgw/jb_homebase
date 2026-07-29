from __future__ import annotations

from pydantic_ai import Agent, ModelRequest, ModelResponse, TextPart, ToolReturnPart, UserPromptPart
from pydantic_ai.capabilities import ProcessHistory
from pydantic_ai.models.anthropic import AnthropicModelSettings
from supabase._async.client import AsyncClient

from jordan_claw.agents.capabilities import resolve_capabilities
from jordan_claw.agents.deps import AgentDeps
from jordan_claw.db.agents import AgentConfig, get_agent_config

# Anthropic prompt caching: automatic caching moves a breakpoint forward with
# the conversation (and covers intra-run tool loops, where each round-trip
# re-sends the whole prefix); instructions and tool definitions get explicit
# breakpoints. The memory context block prepended to instructions is cached
# DB-side and only recomputed when facts change, so the instruction block is
# byte-stable across turns. anthropic_* settings are ignored by non-Anthropic
# models, so a future per-agent model pin doesn't need a branch here.
CACHE_SETTINGS = AnthropicModelSettings(
    anthropic_cache=True,
    anthropic_cache_instructions=True,
    anthropic_cache_tool_definitions=True,
)


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
        name=config.slug,
        instructions=system_prompt,
        capabilities=[
            *resolve_capabilities(config.capabilities),
            ProcessHistory(trim_history_processor),
        ],
        deps_type=AgentDeps,
        model_settings=CACHE_SETTINGS,
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


# Token estimator shared with memory/reader.py: 1 token ≈ 4 chars. The budget
# below is in TOKENS; chars are only the estimation unit (4000 tokens ≈ 16k chars).
CHARS_PER_TOKEN = 4


def trim_history_processor(
    messages: list[ModelRequest | ModelResponse],
    max_tokens: int = 4000,
) -> list[ModelRequest | ModelResponse]:
    """History processor that trims oldest messages to stay within a token budget.

    max_tokens is a real token budget, estimated at CHARS_PER_TOKEN chars per
    token (so the default admits ~16,000 chars, not 4,000).
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

    # The history must open at a user turn: Anthropic rejects a leading
    # assistant message, and a tool_result whose tool_use was trimmed away
    # 400s the whole request ("unexpected tool_use_id"). kept is always a
    # suffix of messages, so move its start to a clean boundary.
    def _is_clean_start(msg: ModelRequest | ModelResponse) -> bool:
        return isinstance(msg, ModelRequest) and not any(
            isinstance(p, ToolReturnPart) for p in msg.parts
        )

    start = len(messages) - len(kept)
    ahead = next((i for i in range(start, len(messages)) if _is_clean_start(messages[i])), None)
    if ahead is not None:
        return messages[ahead:]
    # No user turn inside the budget window (a single oversized tool exchange,
    # e.g. a full FDA label, can exceed the whole budget). The budget goes soft
    # rather than sending an invalid request: walk back to the user turn that
    # opened the stranded exchange. The 200k-token run guardrail still bounds us.
    behind = next((i for i in range(start - 1, -1, -1) if _is_clean_start(messages[i])), None)
    if behind is not None:
        return messages[behind:]
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
