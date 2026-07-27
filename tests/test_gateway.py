from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jordan_claw.analytics.types import AgentRunResult
from jordan_claw.db.agents import AgentConfig
from jordan_claw.gateway.models import IncomingMessage
from jordan_claw.gateway.router import ERROR_RESPONSE, handle_message


def make_agent_config() -> AgentConfig:
    return AgentConfig(
        id="agent-001",
        org_id="1408252a-fd36-4fd3-b527-3b2f495d7b9c",
        name="Claw Main",
        slug="claw-main",
        system_prompt="You are helpful.",
        model="claude-sonnet-4-20250514",
        is_active=True,
    )


def make_incoming(
    content: str = "Hello",
    channel_message_id: str = "app-claw-main-123",
) -> IncomingMessage:
    return IncomingMessage(
        channel="app",
        channel_thread_id="claw-main",
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
    mock_usage.cache_read_tokens = 0
    mock_usage.cache_write_tokens = 0
    mock_usage.requests = 1

    mock_result = MagicMock()
    mock_result.output = "Hello! How can I help?"
    mock_result.usage = mock_usage

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
            "jordan_claw.gateway.router.get_agent_config",
            return_value=make_agent_config(),
        ),
        patch(
            "jordan_claw.gateway.router.create_agent",
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
            "jordan_claw.gateway.router.get_agent_config",
            side_effect=Exception("LLM timeout"),
        ),
        patch(
            "jordan_claw.gateway.router.update_conversation_status",
            return_value=None,
        ),
    ):
        result = await handle_message(
            make_incoming(channel_message_id="app-claw-main-999"),
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
    mock_usage.cache_read_tokens = 0
    mock_usage.cache_write_tokens = 0
    mock_usage.requests = 1

    mock_result = MagicMock()
    mock_result.output = "I remember your preferences."
    mock_result.usage = mock_usage

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
            "jordan_claw.gateway.router.get_agent_config",
            return_value=make_agent_config(),
        ),
        patch(
            "jordan_claw.gateway.router.create_agent",
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

    # Verify memory_context was passed to create_agent
    build_call_kwargs = mock_build.call_args.kwargs
    assert build_call_kwargs.get("memory_context") == "## Memory Context\n- Prefers Python"


@pytest.mark.asyncio
async def test_user_message_metadata_persisted(mock_db):
    """IncomingMessage.metadata rides along on the user-message save.

    Voice stores agent_slug there so a replayed request can recover the
    original route without a fresh classifier call.
    """
    fake_conversation = {"id": "conv-004"}
    mock_save = AsyncMock(return_value={})
    msg = IncomingMessage(
        channel="app-voice",
        channel_thread_id="app-voice",
        channel_message_id="app-voice-utt-1",
        content="log my workout",
        org_id="1408252a-fd36-4fd3-b527-3b2f495d7b9c",
        metadata={"agent_slug": "workout-coach"},
    )

    with (
        patch("jordan_claw.gateway.router.message_exists", return_value=False),
        patch(
            "jordan_claw.gateway.router.get_or_create_conversation",
            return_value=fake_conversation,
        ),
        patch("jordan_claw.gateway.router.save_message", new=mock_save),
        patch("jordan_claw.gateway.router.get_recent_messages", return_value=[]),
        patch("jordan_claw.gateway.router.load_memory_context", return_value=""),
        patch(
            "jordan_claw.gateway.router.get_agent_config",
            side_effect=Exception("LLM timeout"),
        ),
        patch(
            "jordan_claw.gateway.router.update_conversation_status",
            return_value=None,
        ),
    ):
        await handle_message(
            msg,
            db=mock_db,
            agent_slug="workout-coach",
            tavily_api_key="test-key",
            fastmail_username="test@fastmail.com",
            fastmail_app_password="test-password",
        )

    user_save = mock_save.await_args_list[0]
    assert user_save.kwargs["role"] == "user"
    assert user_save.kwargs["metadata"] == {"agent_slug": "workout-coach"}


def _fake_run_result(*, traceparent: str | None) -> AgentRunResult:
    return AgentRunResult(
        output="Hello! How can I help?",
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        cost_usd=None,
        duration_ms=1,
        tool_call_count=0,
        model="claude-sonnet-4-20250514",
        success=True,
        error_type=None,
        traceparent=traceparent,
    )


@pytest.mark.asyncio
async def test_assistant_message_persists_traceparent_metadata(mock_db):
    """The runner's traceparent rides along on the assistant save_message call
    so a later feedback POST can annotate the run's span."""
    fake_conversation = {"id": "conv-005"}
    mock_save = AsyncMock(return_value={})
    traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"

    with (
        patch("jordan_claw.gateway.router.message_exists", return_value=False),
        patch(
            "jordan_claw.gateway.router.get_or_create_conversation",
            return_value=fake_conversation,
        ),
        patch("jordan_claw.gateway.router.save_message", new=mock_save),
        patch("jordan_claw.gateway.router.get_recent_messages", return_value=[]),
        patch("jordan_claw.gateway.router.load_memory_context", return_value=""),
        patch(
            "jordan_claw.gateway.router.get_agent_config",
            return_value=make_agent_config(),
        ),
        patch(
            "jordan_claw.gateway.router.create_agent",
            return_value=(AsyncMock(), "claude-sonnet-4-20250514"),
        ),
        patch(
            "jordan_claw.gateway.router.run_agent_instrumented",
            new=AsyncMock(return_value=_fake_run_result(traceparent=traceparent)),
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

    assert result.traceparent == traceparent
    assistant_save = mock_save.await_args_list[1]
    assert assistant_save.kwargs["role"] == "assistant"
    assert assistant_save.kwargs["metadata"] == {"traceparent": traceparent}


@pytest.mark.asyncio
async def test_assistant_message_metadata_none_when_traceparent_missing(mock_db):
    """Unconfigured logfire yields traceparent=None; the assistant save must not
    write a metadata dict with a null traceparent in that case."""
    fake_conversation = {"id": "conv-006"}
    mock_save = AsyncMock(return_value={})

    with (
        patch("jordan_claw.gateway.router.message_exists", return_value=False),
        patch(
            "jordan_claw.gateway.router.get_or_create_conversation",
            return_value=fake_conversation,
        ),
        patch("jordan_claw.gateway.router.save_message", new=mock_save),
        patch("jordan_claw.gateway.router.get_recent_messages", return_value=[]),
        patch("jordan_claw.gateway.router.load_memory_context", return_value=""),
        patch(
            "jordan_claw.gateway.router.get_agent_config",
            return_value=make_agent_config(),
        ),
        patch(
            "jordan_claw.gateway.router.create_agent",
            return_value=(AsyncMock(), "claude-sonnet-4-20250514"),
        ),
        patch(
            "jordan_claw.gateway.router.run_agent_instrumented",
            new=AsyncMock(return_value=_fake_run_result(traceparent=None)),
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

    assert result.traceparent is None
    assistant_save = mock_save.await_args_list[1]
    assert assistant_save.kwargs["role"] == "assistant"
    assert assistant_save.kwargs["metadata"] is None
