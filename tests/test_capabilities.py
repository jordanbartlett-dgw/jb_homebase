from __future__ import annotations

import pytest
from pydantic_ai import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

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
