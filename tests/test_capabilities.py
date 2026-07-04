from __future__ import annotations

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent, ModelResponse, TextPart
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.toolsets import FunctionToolset

from jordan_claw.agents.capabilities import CAPABILITY_REGISTRY, resolve_capabilities
from jordan_claw.agents.deps import AgentDeps
from jordan_claw.agents.factory import create_agent
from jordan_claw.db.agents import AgentConfig


def test_registry_covers_all_sixteen_tools():
    tool_names = set()
    for group in CAPABILITY_REGISTRY.values():
        tool_names.update(group.toolset.tools)
    assert len(tool_names) == 16


def test_expected_groups_exist():
    assert set(CAPABILITY_REGISTRY) == {"core", "web", "calendar", "memory", "obsidian", "workout"}


def test_resolve_capabilities_maps_ids():
    groups = resolve_capabilities(["core", "workout"])
    assert [g.id for g in groups] == ["core", "workout"]


def test_resolve_capabilities_skips_unknown_with_warning():
    groups = resolve_capabilities(["core", "nonexistent"])
    assert [g.id for g in groups] == ["core"]


@pytest.mark.asyncio
async def test_graceful_agent_completes_plain_run():
    """Guards the end_strategy flip at construction level.

    create_agent no longer pins end_strategy='early'; the v2 default is
    'graceful'. A plain text run must still complete normally.
    """
    config = AgentConfig(
        id="agent-001",
        org_id="org-001",
        name="Test Agent",
        slug="test-agent",
        system_prompt="Be helpful.",
        model="test",
        tools=[],
        capabilities=["core"],
        is_active=True,
    )
    agent, _ = create_agent(config)
    assert agent.end_strategy == "graceful"

    def plain_text(messages, info):
        return ModelResponse(parts=[TextPart(content="hello")])

    deps = AgentDeps(
        org_id="org-001",
        tavily_api_key="test-key",
        fastmail_username="test@example.com",
        fastmail_app_password="test-pass",
    )
    result = await agent.run("hi", deps=deps, model=FunctionModel(plain_text))
    assert result.output == "hello"


# --- Graceful end-strategy semantics (the v2 behavior change we accepted) ---
#
# end_strategy governs function tools requested ALONGSIDE AN OUTPUT TOOL in
# one model response. Plain text next to function tool calls is never final:
# pydantic-ai prioritizes the tool calls and loops, under every strategy.
# So the final output in these tests arrives via the structured-output tool.


class _Answer(BaseModel):
    message: str


def _flag_agent(end_strategy: str) -> tuple[Agent[None, _Answer], dict[str, bool | int]]:
    """Throwaway agent whose model emits a function tool call AND the final
    output tool call in a single response."""
    state: dict[str, bool | int] = {"tool_ran": False, "model_calls": 0}

    def flip_flag() -> str:
        state["tool_ran"] = True
        return "flipped"

    toolset: FunctionToolset[None] = FunctionToolset()
    toolset.add_function(flip_flag, name="flip_flag")

    def both_in_one_response(messages: list, info: AgentInfo) -> ModelResponse:
        state["model_calls"] += 1
        output_tool = info.output_tools[0].name
        return ModelResponse(
            parts=[
                ToolCallPart(tool_name="flip_flag", args="{}", tool_call_id="tc1"),
                ToolCallPart(tool_name=output_tool, args='{"message": "done"}', tool_call_id="tc2"),
            ]
        )

    agent = Agent(
        FunctionModel(both_in_one_response),
        output_type=_Answer,
        toolsets=[toolset],
        end_strategy=end_strategy,  # type: ignore[arg-type]
    )
    return agent, state


@pytest.mark.asyncio
async def test_graceful_executes_tool_alongside_final_output():
    """Under 'graceful' (v2 default, now adopted), a function tool requested
    in the same response as the final output DOES execute."""
    agent, state = _flag_agent("graceful")
    result = await agent.run("go")

    assert result.output == _Answer(message="done")
    assert state["tool_ran"] is True
    assert state["model_calls"] == 1  # run still ends after one round


@pytest.mark.asyncio
async def test_early_skips_tool_alongside_final_output():
    """Contrast: the old 'early' pin skipped that same function tool. This is
    exactly the behavior change accepted in PR2."""
    agent, state = _flag_agent("early")
    result = await agent.run("go")

    assert result.output == _Answer(message="done")
    assert state["tool_ran"] is False
    assert state["model_calls"] == 1


@pytest.mark.asyncio
async def test_text_alongside_tool_call_is_never_final():
    """A TextPart next to a function tool call is not a final output under any
    strategy: the tool executes and the run continues for another round."""
    state = {"tool_ran": False, "model_calls": 0}

    def flip_flag() -> str:
        state["tool_ran"] = True
        return "flipped"

    toolset: FunctionToolset[None] = FunctionToolset()
    toolset.add_function(flip_flag, name="flip_flag")

    def tool_then_text(messages: list, info: AgentInfo) -> ModelResponse:
        state["model_calls"] += 1
        if state["model_calls"] == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(tool_name="flip_flag", args="{}", tool_call_id="tc1"),
                    TextPart(content="this text is ignored as output"),
                ]
            )
        return ModelResponse(parts=[TextPart(content="actual final answer")])

    agent = Agent(FunctionModel(tool_then_text), toolsets=[toolset])
    result = await agent.run("go")

    assert state["tool_ran"] is True
    assert state["model_calls"] == 2  # a second round produced the real output
    assert result.output == "actual final answer"
