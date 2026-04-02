from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from pydantic_ai import ModelRequest, ModelResponse

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.agents.factory import db_messages_to_history
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
