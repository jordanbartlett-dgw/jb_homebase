from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jordan_claw.gateway.models import IncomingMessage
from jordan_claw.gateway.router import ERROR_RESPONSE, handle_message


def make_incoming(
    content: str = "Hello",
    channel_message_id: str = "telegram:123",
) -> IncomingMessage:
    return IncomingMessage(
        channel="telegram",
        channel_thread_id="chat_456",
        channel_message_id=channel_message_id,
        content=content,
        org_id="1408252a-fd36-4fd3-b527-3b2f495d7b9c",
    )


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.mark.asyncio
async def test_duplicate_message_returns_empty(mock_db):
    """Duplicate messages should be skipped."""
    with patch("jordan_claw.gateway.router.message_exists", return_value=True):
        result = await handle_message(
            make_incoming(),
            db=mock_db,
            agent_slug="claw-main",
            tavily_api_key="test-key",
            fastmail_username="test@fastmail.com",
            fastmail_app_password="test-password",
        )

    assert result.content == ""
    assert result.conversation_id == ""


@pytest.mark.asyncio
async def test_successful_message_flow(mock_db):
    """A normal message should go through the full lifecycle and return a response."""
    fake_conversation = {"id": "conv-001"}
    fake_messages = [
        {
            "role": "user",
            "content": "Hi",
            "created_at": "2026-01-01T00:00:00Z",
            "token_count": None,
            "model": None,
            "metadata": {},
        },
    ]

    mock_usage = MagicMock()
    mock_usage.input_tokens = 10
    mock_usage.output_tokens = 5
    mock_usage.requests = 1

    mock_result = MagicMock()
    mock_result.output = "Hello! How can I help?"
    mock_result.usage.return_value = mock_usage

    mock_agent = AsyncMock()
    mock_agent.run.return_value = mock_result

    with (
        patch("jordan_claw.gateway.router.message_exists", return_value=False),
        patch(
            "jordan_claw.gateway.router.get_or_create_conversation",
            return_value=fake_conversation,
        ),
        patch("jordan_claw.gateway.router.save_message", return_value={}),
        patch(
            "jordan_claw.gateway.router.get_recent_messages",
            return_value=fake_messages,
        ),
        patch("jordan_claw.gateway.router.load_memory_context", return_value=""),
        patch(
            "jordan_claw.gateway.router.build_agent",
            return_value=(mock_agent, "claude-sonnet-4-20250514"),
        ),
        patch(
            "jordan_claw.gateway.router.extract_memory_background",
            new_callable=AsyncMock,
        ),
    ):
        result = await handle_message(
            make_incoming(),
            db=mock_db,
            agent_slug="claw-main",
            tavily_api_key="test-key",
            fastmail_username="test@fastmail.com",
            fastmail_app_password="test-password",
        )

    assert result.content == "Hello! How can I help?"
    assert result.conversation_id == "conv-001"
    assert result.token_count == 15
    assert result.model == "claude-sonnet-4-20250514"

    call_kwargs = mock_agent.run.call_args.kwargs
    assert "deps" in call_kwargs
    assert call_kwargs["deps"].org_id == "1408252a-fd36-4fd3-b527-3b2f495d7b9c"
    assert call_kwargs["deps"].tavily_api_key == "test-key"
    assert call_kwargs["deps"].supabase_client is mock_db


@pytest.mark.asyncio
async def test_agent_error_returns_friendly_message(mock_db):
    """Agent failures should return a user-friendly error, not crash."""
    fake_conversation = {"id": "conv-002"}

    with (
        patch("jordan_claw.gateway.router.message_exists", return_value=False),
        patch(
            "jordan_claw.gateway.router.get_or_create_conversation",
            return_value=fake_conversation,
        ),
        patch("jordan_claw.gateway.router.save_message", return_value={}),
        patch("jordan_claw.gateway.router.get_recent_messages", return_value=[]),
        patch("jordan_claw.gateway.router.load_memory_context", return_value=""),
        patch(
            "jordan_claw.gateway.router.build_agent",
            side_effect=Exception("LLM timeout"),
        ),
        patch(
            "jordan_claw.gateway.router.update_conversation_status",
            return_value=None,
        ),
    ):
        result = await handle_message(
            make_incoming(channel_message_id="telegram:999"),
            db=mock_db,
            agent_slug="claw-main",
            tavily_api_key="test-key",
            fastmail_username="test@fastmail.com",
            fastmail_app_password="test-password",
        )

    assert result.content == ERROR_RESPONSE
    assert result.conversation_id == "conv-002"


@pytest.mark.asyncio
async def test_memory_context_injected_into_agent(mock_db):
    """Memory context should be passed to build_agent."""
    fake_conversation = {"id": "conv-003"}

    mock_usage = MagicMock()
    mock_usage.input_tokens = 10
    mock_usage.output_tokens = 5
    mock_usage.requests = 1

    mock_result = MagicMock()
    mock_result.output = "I remember your preferences."
    mock_result.usage.return_value = mock_usage

    mock_agent = AsyncMock()
    mock_agent.run.return_value = mock_result

    with (
        patch("jordan_claw.gateway.router.message_exists", return_value=False),
        patch(
            "jordan_claw.gateway.router.get_or_create_conversation",
            return_value=fake_conversation,
        ),
        patch("jordan_claw.gateway.router.save_message", return_value={}),
        patch("jordan_claw.gateway.router.get_recent_messages", return_value=[]),
        patch(
            "jordan_claw.gateway.router.load_memory_context",
            return_value="## Memory Context\n- Prefers Python",
        ),
        patch(
            "jordan_claw.gateway.router.build_agent",
            return_value=(mock_agent, "claude-sonnet-4-20250514"),
        ) as mock_build,
        patch(
            "jordan_claw.gateway.router.extract_memory_background",
            new_callable=AsyncMock,
        ),
    ):
        await handle_message(
            make_incoming(),
            db=mock_db,
            agent_slug="claw-main",
            tavily_api_key="test-key",
            fastmail_username="test@fastmail.com",
            fastmail_app_password="test-password",
        )

    # Verify memory_context was passed to build_agent
    build_call_kwargs = mock_build.call_args.kwargs
    assert build_call_kwargs.get("memory_context") == "## Memory Context\n- Prefers Python"
