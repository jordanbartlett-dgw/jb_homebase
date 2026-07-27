from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai import ModelRequest, ModelResponse
from pydantic_ai.messages import TextPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.agents.factory import build_agent, create_agent, db_messages_to_history
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
                "capabilities": ["core", "web"],
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
    assert config.capabilities == ["core", "web"]
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


def test_resolve_model_order():
    from jordan_claw.db.agents import resolve_model

    # Per-agent override wins over the org default.
    assert resolve_model("anthropic:claude-haiku-4-5", "anthropic:claude-sonnet-5") == (
        "anthropic:claude-haiku-4-5"
    )
    # NULL agent model falls back to the org default.
    assert resolve_model(None, "anthropic:claude-sonnet-5") == "anthropic:claude-sonnet-5"
    # Neither set is a hard misconfig.
    with pytest.raises(ValueError, match="No model configured"):
        resolve_model(None, None)


def _table_router(tables: dict[str, list[dict]]) -> MagicMock:
    def table(name: str) -> MagicMock:
        mock_query = MagicMock()
        mock_query.execute = AsyncMock(return_value=MagicMock(data=tables.get(name, [])))
        mock_query.eq.return_value = mock_query
        mock_query.select.return_value = mock_query
        mock_query.limit.return_value = mock_query
        return mock_query

    mock_db = MagicMock()
    mock_db.table.side_effect = table
    return mock_db


@pytest.mark.asyncio
async def test_get_agent_config_null_model_resolves_org_default():
    """Post-020 shape: agents.model is NULL, organizations.default_model rules."""
    mock_db = _table_router(
        {
            "agents": [
                {
                    "id": "agent-001",
                    "org_id": "org-001",
                    "name": "Test Agent",
                    "slug": "test-agent",
                    "system_prompt": "You are helpful.",
                    "model": None,
                    "capabilities": ["core"],
                    "is_active": True,
                }
            ],
            "organizations": [{"default_model": "anthropic:claude-sonnet-5"}],
        }
    )
    config = await get_agent_config(mock_db, "org-001", "test-agent")
    assert config.model == "anthropic:claude-sonnet-5"


@pytest.mark.asyncio
async def test_get_agent_config_override_beats_org_default():
    mock_db = _table_router(
        {
            "agents": [
                {
                    "id": "agent-001",
                    "org_id": "org-001",
                    "name": "Test Agent",
                    "slug": "test-agent",
                    "system_prompt": "You are helpful.",
                    "model": "anthropic:claude-haiku-4-5",
                    "capabilities": ["core"],
                    "is_active": True,
                }
            ],
            "organizations": [{"default_model": "anthropic:claude-sonnet-5"}],
        }
    )
    config = await get_agent_config(mock_db, "org-001", "test-agent")
    assert config.model == "anthropic:claude-haiku-4-5"


@pytest.mark.asyncio
async def test_build_agent_uses_db_config():
    fake_config = AgentConfig(
        id="agent-001",
        org_id="org-001",
        name="Test Agent",
        slug="test-agent",
        system_prompt="Be helpful.",
        model="test",
        capabilities=["core", "web"],
        is_active=True,
    )

    mock_db = AsyncMock()

    with patch("jordan_claw.agents.factory.get_agent_config", return_value=fake_config):
        agent, model_name = await build_agent(mock_db, "org-001", "test-agent")

    assert model_name == "test"

    test_model = TestModel(call_tools=[])  # send tool defs to the model, invoke none
    deps = AgentDeps(
        org_id="org-001",
        tavily_api_key="test-key",
        fastmail_username="test@example.com",
        fastmail_app_password="test-pass",
    )
    await agent.run("hi", deps=deps, model=test_model)

    sent_tools = {t.name for t in test_model.last_model_request_parameters.function_tools}
    # fetch_article proves capabilities drive the toolset, not the legacy tools list.
    assert sent_tools == {"current_datetime", "search_web", "fetch_article"}


def test_create_agent_sets_name_from_slug():
    """Without an explicit name, pydantic-ai infers it from the caller's local
    variable ("agent" everywhere create_agent is called), collapsing every
    online-eval target into one bucket. name must come from config.slug."""
    fake_config = AgentConfig(
        id="agent-001",
        org_id="org-001",
        name="Test Agent",
        slug="test-agent",
        system_prompt="Be helpful.",
        model="test",
        capabilities=[],
        is_active=True,
    )

    agent, _ = create_agent(fake_config)

    assert agent.name == "test-agent"


@pytest.mark.asyncio
async def test_build_agent_skips_unknown_capabilities():
    fake_config = AgentConfig(
        id="agent-001",
        org_id="org-001",
        name="Test Agent",
        slug="test-agent",
        system_prompt="Be helpful.",
        model="test",
        capabilities=["core", "nonexistent"],
        is_active=True,
    )

    mock_db = AsyncMock()

    with patch("jordan_claw.agents.factory.get_agent_config", return_value=fake_config):
        agent, model_name = await build_agent(mock_db, "org-001", "test-agent")

    assert model_name == "test"

    test_model = TestModel(call_tools=[])  # send tool defs to the model, invoke none
    deps = AgentDeps(
        org_id="org-001",
        tavily_api_key="test-key",
        fastmail_username="test@example.com",
        fastmail_app_password="test-pass",
    )
    await agent.run("hi", deps=deps, model=test_model)

    sent_tools = {t.name for t in test_model.last_model_request_parameters.function_tools}
    # "nonexistent" is not in CAPABILITY_REGISTRY, so only core's tool reaches the model.
    # resolve_capabilities logs a warning for unknown capability ids.
    assert sent_tools == {"current_datetime"}


def test_trim_history_processor_strips_orphaned_tool_results():
    """trim_history_processor should strip leading ToolReturnPart messages after trimming."""
    from pydantic_ai import ToolReturnPart
    from pydantic_ai.messages import ToolCallPart

    from jordan_claw.agents.factory import trim_history_processor

    messages = [
        ModelRequest(parts=[UserPromptPart(content="A" * 4000)]),
        ModelResponse(parts=[ToolCallPart(tool_name="search_web", args="", tool_call_id="tc1")]),
        ModelRequest(
            parts=[ToolReturnPart(tool_name="search_web", content="result", tool_call_id="tc1")]
        ),
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


def test_trim_history_processor_never_strands_midrun_tool_exchange():
    """One oversized tool return mid-run must not produce a history that opens
    with an orphaned tool_result (Anthropic 400: unexpected tool_use_id).

    Prod repro (med-check, 2026-07-25): first user turn -> model calls a tool ->
    tool returns ~17k chars -> trim drops the user turn and the tool_use response,
    leaving only the tool_result. The budget must go soft instead: keep the
    exchange intact back to the user turn that opened it.
    """
    from pydantic_ai import ToolReturnPart
    from pydantic_ai.messages import ToolCallPart

    from jordan_claw.agents.factory import trim_history_processor

    messages = [
        ModelRequest(parts=[UserPromptPart(content="can you check ondansetron?")]),
        ModelResponse(
            parts=[ToolCallPart(tool_name="fetch_fda_label", args="", tool_call_id="tc1")]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(tool_name="fetch_fda_label", content="X" * 17000, tool_call_id="tc1")
            ]
        ),
    ]
    result = trim_history_processor(messages, max_tokens=4000)

    # The whole exchange survives, starting at the user turn.
    assert isinstance(result[0], ModelRequest)
    assert any(isinstance(p, UserPromptPart) for p in result[0].parts)
    # Every tool_result still has its tool_use in the history.
    call_ids = {
        p.tool_call_id
        for m in result
        if isinstance(m, ModelResponse)
        for p in m.parts
        if isinstance(p, ToolCallPart)
    }
    return_ids = {
        p.tool_call_id
        for m in result
        if isinstance(m, ModelRequest)
        for p in m.parts
        if isinstance(p, ToolReturnPart)
    }
    assert return_ids <= call_ids


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


def test_trim_budget_is_tokens_not_chars():
    """The budget unit is tokens (est. 4 chars/token), not raw characters.

    8,800 chars ≈ 2,200 tokens fits comfortably in the default 4000-token
    budget. If the budget were ever misapplied as a character count, most of
    this history would be silently dropped — this pins the unit semantics.
    """
    from jordan_claw.agents.factory import trim_history_processor

    messages = []
    for i in range(4):
        messages.append(ModelRequest(parts=[UserPromptPart(content=f"u{i}" + "x" * 1100)]))
        messages.append(ModelResponse(parts=[TextPart(content=f"a{i}" + "y" * 1100)]))

    result = trim_history_processor(messages)

    # ~8,800 chars total: over a 4000-CHAR budget, under a 4000-TOKEN budget.
    assert result == messages


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
        ModelRequest(
            parts=[ToolReturnPart(tool_name="search_notes", content="x" * 2000, tool_call_id="tc1")]
        ),
    ]
    result = trim_history_processor(messages, max_tokens=4000)

    assert len(result) >= 1


@pytest.mark.asyncio
async def test_trim_history_runs_inside_agent_run():
    """ProcessHistory must actually trim history during a run, not just exist.

    Guards the v2 capabilities wiring in create_agent: a FunctionModel captures
    what the model receives after a long history passes through the agent.
    """
    fake_config = AgentConfig(
        id="agent-001",
        org_id="org-001",
        name="Test Agent",
        slug="test-agent",
        system_prompt="Be helpful.",
        model="test",
        capabilities=[],
        is_active=True,
    )
    agent, _ = create_agent(fake_config)

    received: list = []

    def capture(messages, info):
        received.extend(messages)
        return ModelResponse(parts=[TextPart(content="ok")])

    history = []
    for i in range(6):
        history.append(ModelRequest(parts=[UserPromptPart(content=f"u{i} " + "x" * 3000)]))
        history.append(ModelResponse(parts=[TextPart(content=f"a{i} " + "x" * 3000)]))

    deps = AgentDeps(
        org_id="org-001",
        tavily_api_key="test-key",
        fastmail_username="test@example.com",
        fastmail_app_password="test-pass",
    )
    await agent.run(
        "new question",
        deps=deps,
        message_history=history,
        model=FunctionModel(capture),
    )

    received_text = str(received)
    assert "u5" in received_text  # newest exchange survives
    assert "u0" not in received_text  # oldest trimmed by the 4000-token budget
