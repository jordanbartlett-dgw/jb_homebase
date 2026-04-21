from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai import ModelRequest, ModelResponse
from pydantic_ai.messages import TextPart, UserPromptPart

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.agents.factory import build_agent, db_messages_to_history
from jordan_claw.db.agents import AgentConfig, get_agent_config


def test_agent_deps_construction():
    deps = AgentDeps(
        org_id="test-org",
        tavily_api_key="tavily-key",
        fastmail_username="user@fastmail.com",
        fastmail_app_password="app-pass",
    )
    assert deps.org_id == "test-org"
    assert deps.tavily_api_key == "tavily-key"
    assert deps.supabase_client is None


def test_empty_history():
    result = db_messages_to_history([])
    assert result == []


def test_user_and_assistant_messages():
    db_rows = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
        {"role": "user", "content": "What time is it?"},
    ]
    result = db_messages_to_history(db_rows)

    assert len(result) == 3
    assert isinstance(result[0], ModelRequest)
    assert result[0].parts[0].content == "Hello"
    assert isinstance(result[1], ModelResponse)
    assert result[1].parts[0].content == "Hi there!"
    assert isinstance(result[2], ModelRequest)


def test_system_and_tool_roles_skipped():
    db_rows = [
        {"role": "system", "content": "You are helpful"},
        {"role": "user", "content": "Hello"},
        {"role": "tool", "content": "tool output"},
        {"role": "assistant", "content": "Hi"},
    ]
    result = db_messages_to_history(db_rows)

    assert len(result) == 2
    assert isinstance(result[0], ModelRequest)
    assert isinstance(result[1], ModelResponse)


@pytest.mark.asyncio
async def test_get_agent_config_returns_typed_config():
    # Mock the Supabase query builder chain:
    # client.table("agents").select(...).eq(...).eq(...).eq(...).limit(...).execute()
    mock_result = MagicMock(
        data=[
            {
                "id": "agent-001",
                "org_id": "org-001",
                "name": "Test Agent",
                "slug": "test-agent",
                "system_prompt": "You are helpful.",
                "model": "claude-sonnet-4-20250514",
                "tools": ["current_datetime", "search_web"],
                "is_active": True,
            }
        ]
    )

    # Build the mock chain from right to left
    mock_query = MagicMock()
    mock_query.execute = AsyncMock(return_value=mock_result)
    mock_query.limit.return_value = mock_query
    mock_query.eq.return_value = mock_query
    mock_query.select.return_value = mock_query

    mock_db = MagicMock()
    mock_db.table.return_value = mock_query

    config = await get_agent_config(mock_db, "org-001", "test-agent")

    assert isinstance(config, AgentConfig)
    assert config.slug == "test-agent"
    assert config.tools == ["current_datetime", "search_web"]
    assert config.system_prompt == "You are helpful."


@pytest.mark.asyncio
async def test_get_agent_config_not_found_raises():
    # Mock the Supabase query builder chain with empty data
    mock_result = MagicMock(data=[])

    mock_query = MagicMock()
    mock_query.execute = AsyncMock(return_value=mock_result)
    mock_query.limit.return_value = mock_query
    mock_query.eq.return_value = mock_query
    mock_query.select.return_value = mock_query

    mock_db = MagicMock()
    mock_db.table.return_value = mock_query

    with pytest.raises(ValueError, match="Agent not found"):
        await get_agent_config(mock_db, "org-001", "missing-agent")


@pytest.mark.asyncio
async def test_build_agent_uses_db_config():
    fake_config = AgentConfig(
        id="agent-001",
        org_id="org-001",
        name="Test Agent",
        slug="test-agent",
        system_prompt="Be helpful.",
        model="test",
        tools=["current_datetime", "search_web"],
        is_active=True,
    )

    mock_db = AsyncMock()

    with patch("jordan_claw.agents.factory.get_agent_config", return_value=fake_config):
        agent, model_name = await build_agent(mock_db, "org-001", "test-agent")

    assert model_name == "test"
    from pydantic_ai.tools import ToolDefinition
    from pydantic_ai.toolsets.filtered import FilteredToolset

    ts = agent._user_toolsets[0]
    assert isinstance(ts, FilteredToolset)

    def _allows(name: str) -> bool:
        td = ToolDefinition(name=name, description="", parameters_json_schema={})
        return ts.filter_func(None, td)

    assert _allows("current_datetime")
    assert _allows("search_web")
    assert not _allows("check_calendar")


def test_history_budget_truncates_oldest_messages():
    """When messages exceed token budget, oldest are dropped."""
    db_rows = [
        {"role": "user", "content": "A" * 4000},  # ~1000 tokens
        {"role": "assistant", "content": "B" * 4000},  # ~1000 tokens
        {"role": "user", "content": "C" * 4000},  # ~1000 tokens
        {"role": "assistant", "content": "D" * 4000},  # ~1000 tokens
        {"role": "user", "content": "E" * 400},  # ~100 tokens
        {"role": "assistant", "content": "F" * 400},  # ~100 tokens
    ]
    # Budget of 2200 tokens (~8800 chars) should keep the last 2 exchanges
    result = db_messages_to_history(db_rows, max_tokens=2200)

    assert len(result) == 4  # messages 3-6 kept
    assert isinstance(result[0], ModelRequest)
    assert result[0].parts[0].content == "C" * 4000
    assert isinstance(result[-1], ModelResponse)
    assert result[-1].parts[0].content == "F" * 400


def test_history_budget_preserves_most_recent_exchange():
    """Even with a tiny budget, the most recent user+assistant pair is kept."""
    db_rows = [
        {"role": "user", "content": "A" * 40000},  # ~10000 tokens, way over budget
        {"role": "assistant", "content": "B" * 40000},  # ~10000 tokens
    ]
    result = db_messages_to_history(db_rows, max_tokens=100)

    # Must keep at least the most recent exchange regardless of budget
    assert len(result) == 2
    assert isinstance(result[0], ModelRequest)
    assert isinstance(result[1], ModelResponse)


def test_history_no_budget_returns_all():
    """When max_tokens is 0 (disabled), all messages are returned."""
    db_rows = [
        {"role": "user", "content": "A" * 40000},
        {"role": "assistant", "content": "B" * 40000},
        {"role": "user", "content": "C" * 40000},
        {"role": "assistant", "content": "D" * 40000},
    ]
    result = db_messages_to_history(db_rows, max_tokens=0)
    assert len(result) == 4


@pytest.mark.asyncio
async def test_build_agent_skips_unknown_tools():
    fake_config = AgentConfig(
        id="agent-001",
        org_id="org-001",
        name="Test Agent",
        slug="test-agent",
        system_prompt="Be helpful.",
        model="test",
        tools=["current_datetime", "nonexistent_tool"],
        is_active=True,
    )

    mock_db = AsyncMock()

    with patch("jordan_claw.agents.factory.get_agent_config", return_value=fake_config):
        agent, model_name = await build_agent(mock_db, "org-001", "test-agent")

    assert model_name == "test"
    from pydantic_ai.tools import ToolDefinition
    from pydantic_ai.toolsets.filtered import FilteredToolset

    ts = agent._user_toolsets[0]
    assert isinstance(ts, FilteredToolset)

    def _allows(name: str) -> bool:
        td = ToolDefinition(name=name, description="", parameters_json_schema={})
        return ts.filter_func(None, td)

    assert _allows("current_datetime")
    # The filter includes nonexistent_tool by name — but BASE_TOOLSET won't have it,
    # so it won't appear at runtime. The factory logs a warning for unknown tool names.
    assert not _allows("check_calendar")


def test_base_toolset_has_all_registered_tools():
    """BASE_TOOLSET should contain all 10 tools."""
    from jordan_claw.tools import BASE_TOOLSET

    expected_tools = {
        "current_datetime",
        "search_web",
        "check_calendar",
        "schedule_event",
        "recall_memory",
        "forget_memory",
        "search_notes",
        "read_note",
        "create_source_note",
        "fetch_article",
    }
    # FunctionToolset exposes tool names via .tools (a dict keyed by name)
    registered = set(BASE_TOOLSET.tools.keys())
    assert registered == expected_tools


@pytest.mark.asyncio
async def test_build_agent_uses_filtered_toolset():
    """build_agent should use FilteredToolset to scope tools per config."""
    fake_config = AgentConfig(
        id="agent-001",
        org_id="org-001",
        name="Test Agent",
        slug="test-agent",
        system_prompt="Be helpful.",
        model="test",
        tools=["current_datetime", "search_web"],
        is_active=True,
    )

    mock_db = AsyncMock()

    with patch("jordan_claw.agents.factory.get_agent_config", return_value=fake_config):
        agent, model_name = await build_agent(mock_db, "org-001", "test-agent")

    assert model_name == "test"
    from pydantic_ai.tools import ToolDefinition
    from pydantic_ai.toolsets.filtered import FilteredToolset

    ts = agent._user_toolsets[0]
    assert isinstance(ts, FilteredToolset)

    def _allows(name: str) -> bool:
        td = ToolDefinition(name=name, description="", parameters_json_schema={})
        return ts.filter_func(None, td)

    assert _allows("current_datetime")
    assert _allows("search_web")
    assert not _allows("check_calendar")


def test_history_budget_no_orphan_response_at_start():
    """History should never start with an assistant message (ModelResponse)."""
    db_rows = [
        {"role": "user", "content": "A" * 4000},
        {"role": "assistant", "content": "B" * 4000},
        {"role": "user", "content": "C" * 400},  # current unanswered turn
    ]
    result = db_messages_to_history(db_rows, max_tokens=300)

    # First message must always be a user message (ModelRequest)
    assert len(result) >= 1
    assert isinstance(result[0], ModelRequest)


def test_trim_history_processor_strips_orphaned_tool_results():
    """trim_history_processor should strip leading ToolReturnPart messages after trimming."""
    from pydantic_ai import ToolReturnPart
    from pydantic_ai.messages import ToolCallPart

    from jordan_claw.agents.factory import trim_history_processor

    messages = [
        ModelRequest(parts=[UserPromptPart(content="A" * 4000)]),
        ModelResponse(parts=[ToolCallPart(tool_name="search_web", args="", tool_call_id="tc1")]),
        ModelRequest(parts=[ToolReturnPart(tool_name="search_web", content="result", tool_call_id="tc1")]),
        ModelResponse(parts=[TextPart(content="B" * 4000)]),
        ModelRequest(parts=[UserPromptPart(content="C" * 400)]),
        ModelResponse(parts=[TextPart(content="D" * 400)]),
    ]
    # Budget tight enough to drop first user message + tool_use, leaving orphaned tool_result
    result = trim_history_processor(messages, max_tokens=1500)

    # Should NOT start with a ToolReturnPart
    assert len(result) >= 1
    assert isinstance(result[0], ModelRequest)
    assert all(isinstance(p, UserPromptPart) for p in result[0].parts)


def test_trim_history_processor_trims_to_budget():
    """trim_history_processor should drop oldest messages to stay within token budget."""
    from jordan_claw.agents.factory import trim_history_processor

    messages = [
        ModelRequest(parts=[UserPromptPart(content="A" * 4000)]),  # ~1000 tokens
        ModelResponse(parts=[TextPart(content="B" * 4000)]),  # ~1000 tokens
        ModelRequest(parts=[UserPromptPart(content="C" * 4000)]),  # ~1000 tokens
        ModelResponse(parts=[TextPart(content="D" * 4000)]),  # ~1000 tokens
        ModelRequest(parts=[UserPromptPart(content="E" * 400)]),  # ~100 tokens
        ModelResponse(parts=[TextPart(content="F" * 400)]),  # ~100 tokens
    ]
    result = trim_history_processor(messages)

    # Default budget is 4000 tokens (16000 chars). Total is ~4200 tokens.
    # Should drop the first exchange to fit.
    assert len(result) == 4
    assert isinstance(result[0], ModelRequest)
    assert result[0].parts[0].content == "C" * 4000


def test_trim_history_processor_never_returns_empty():
    """trim_history_processor must never return empty even if all messages are tool-related.

    Regression: pydantic-ai calls history processor mid-run after tool use. The in-flight
    history may contain only ToolCallPart/ToolReturnPart messages. The stripping loop must
    not remove all of them, or pydantic-ai raises 'Processed history cannot be empty.'
    """
    from pydantic_ai import ToolReturnPart
    from pydantic_ai.messages import ToolCallPart

    from jordan_claw.agents.factory import trim_history_processor

    # Simulate in-flight history: only tool call + tool return (no user prompt)
    messages = [
        ModelResponse(parts=[ToolCallPart(tool_name="search_notes", args="", tool_call_id="tc1")]),
        ModelRequest(parts=[ToolReturnPart(tool_name="search_notes", content="x" * 2000, tool_call_id="tc1")]),
    ]
    result = trim_history_processor(messages, max_tokens=4000)

    assert len(result) >= 1
