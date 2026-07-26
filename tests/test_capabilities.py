from __future__ import annotations

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent, ModelResponse, TextPart
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.toolsets import FunctionToolset

from jordan_claw.agents.capabilities import CAPABILITY_REGISTRY, ToolGroup, resolve_capabilities
from jordan_claw.agents.deps import AgentDeps
from jordan_claw.agents.factory import create_agent
from jordan_claw.db.agents import AgentConfig


def test_tool_counts_ignore_non_toolgroup_capabilities():
    """CodeMode contributes no ToolGroup tools; counts cover ToolGroups only."""
    tool_names = set()
    for group in CAPABILITY_REGISTRY.values():
        if isinstance(group, ToolGroup):
            tool_names.update(group.toolset.tools)
    assert len(tool_names) == 37


def test_expected_groups_exist():
    assert set(CAPABILITY_REGISTRY) == {
        "core",
        "web",
        "calendar",
        "memory",
        "obsidian",
        "workout",
        "workout_readonly",
        "obsidian_readonly",
        "reminders",
        "meds",
        "email",
        "code_mode",
    }


def test_readonly_groups_expose_no_write_tools():
    """workout_readonly and obsidian_readonly must stay read-only. Reads reuse
    the same fns as the full groups; writes must never leak in."""
    assert set(CAPABILITY_REGISTRY["workout_readonly"].toolset.tools) == {
        "get_workout_profile",
        "get_workout_plan",
        "get_recent_workouts",
    }
    assert set(CAPABILITY_REGISTRY["obsidian_readonly"].toolset.tools) == {
        "search_notes",
        "read_note",
    }


def test_resolve_capabilities_maps_ids():
    groups = resolve_capabilities(["core", "workout"])
    assert [g.id for g in groups] == ["core", "workout"]


def test_resolve_capabilities_skips_unknown_with_warning():
    groups = resolve_capabilities(["core", "nonexistent"])
    assert [g.id for g in groups] == ["core"]


def _prod_shaped_config(slug: str, capabilities: list[str]) -> AgentConfig:
    return AgentConfig(
        id=f"agent-{slug}",
        org_id="org-001",
        name=slug,
        slug=slug,
        system_prompt="Be helpful.",
        model="test",
        capabilities=capabilities,
        is_active=True,
    )


_TEST_DEPS = AgentDeps(
    org_id="org-001",
    tavily_api_key="test-key",
    fastmail_username="test@example.com",
    fastmail_app_password="test-pass",
)


async def _sent_tools(config: AgentConfig) -> set[str]:
    agent, _ = create_agent(config)
    test_model = TestModel(call_tools=[])  # send tool defs to the model, invoke none
    await agent.run("hi", deps=_TEST_DEPS, model=test_model)
    return {t.name for t in test_model.last_model_request_parameters.function_tools}


@pytest.mark.asyncio
async def test_claw_main_gets_workout_reads_but_no_workout_writes():
    """Wiring proof for the prod claw-main capability list after the
    workout_readonly (015) and reminders (017) grants."""
    sent = await _sent_tools(
        _prod_shaped_config(
            "claw-main",
            ["core", "web", "calendar", "memory", "obsidian", "workout_readonly", "reminders"],
        )
    )
    assert {"get_workout_profile", "get_workout_plan", "get_recent_workouts"} <= sent
    assert {"set_reminder", "list_reminders", "cancel_reminder"} <= sent
    writes = {"log_workout", "amend_last_workout", "save_workout_plan", "save_workout_profile"}
    assert not sent & writes


@pytest.mark.asyncio
async def test_workout_coach_gets_note_reads_but_no_note_writes():
    """Wiring proof for the prod workout-coach capability list after the
    obsidian_readonly grant (migration 015)."""
    sent = await _sent_tools(
        _prod_shaped_config(
            "workout-coach", ["core", "calendar", "memory", "workout", "obsidian_readonly"]
        )
    )
    assert {"search_notes", "read_note"} <= sent
    assert "create_source_note" not in sent
    assert "fetch_article" not in sent


@pytest.mark.asyncio
async def test_med_check_capabilities_reach_the_model():
    """Wiring proof: an agent granted core+meds sends all meds tool defs to the model."""
    sent = await _sent_tools(_prod_shaped_config("med-check", ["core", "meds"]))
    assert {
        "normalize_medication",
        "fetch_fda_label",
        "get_medication_profile",
        "save_medication_profile",
        "log_health_event",
        "amend_last_health_event",
        "get_health_events",
        "get_last_visit_date",
        "create_timeline_note",
        "get_care_profile",
        "save_care_profile",
        "save_care_document",
        "check_care_docs_current",
        "current_datetime",
    } <= sent


@pytest.mark.asyncio
async def test_email_capability_reaches_the_model():
    """Wiring proof: an agent granted email sends all four email tool defs."""
    sent = await _sent_tools(_prod_shaped_config("claw-main", ["core", "email"]))
    assert {
        "send_email",
        "reply_to_email",
        "list_email_threads",
        "read_email_thread",
    } <= sent


@pytest.mark.asyncio
async def test_code_mode_replaces_tools_with_run_code():
    """Wiring proof: with code_mode granted, the model sees run_code and the
    wrapped tools are no longer sent as individual function tools."""
    sent = await _sent_tools(_prod_shaped_config("claw-main", ["core", "web", "code_mode"]))
    assert "run_code" in sent
    assert "search_web" not in sent


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
