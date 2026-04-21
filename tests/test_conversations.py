from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from jordan_claw.db.conversations import get_or_create_conversation

ORG_ID = "org-001"
CHANNEL = "telegram"
THREAD_ID = "chat_123"


def _mock_db(conversation_data=None, last_message_time=None):
    """Build a mock Supabase client for conversation queries.

    conversation_data: list of conversation rows to return from the conversations query.
    last_message_time: ISO timestamp string for the most recent message, or None for no messages.
    """
    mock_db = MagicMock()

    # conversations table query chain
    conv_query = MagicMock()
    conv_result = MagicMock(data=conversation_data or [])
    conv_query.execute = AsyncMock(return_value=conv_result)
    conv_query.limit.return_value = conv_query
    conv_query.eq.return_value = conv_query
    conv_query.select.return_value = conv_query

    # messages table query chain (for last message timestamp)
    msg_query = MagicMock()
    if last_message_time:
        msg_result = MagicMock(data=[{"created_at": last_message_time}])
    else:
        msg_result = MagicMock(data=[])
    msg_query.execute = AsyncMock(return_value=msg_result)
    msg_query.limit.return_value = msg_query
    msg_query.order.return_value = msg_query
    msg_query.eq.return_value = msg_query
    msg_query.select.return_value = msg_query

    # insert chain (for creating new conversations)
    insert_query = MagicMock()
    insert_result = MagicMock(data=[{"id": "new-conv", "status": "active"}])
    insert_query.execute = AsyncMock(return_value=insert_result)
    insert_query.insert = MagicMock(return_value=insert_query)

    # update chain (for closing stale conversations)
    update_query = MagicMock()
    update_result = MagicMock(data=[])
    update_query.execute = AsyncMock(return_value=update_result)
    update_query.eq.return_value = update_query
    update_query.update = MagicMock(return_value=update_query)

    def table_router(name):
        if name == "conversations":
            # Return different mocks depending on whether it's a select or insert/update
            # We chain them so the first call is select, subsequent are insert/update
            chain = MagicMock()
            chain.select = conv_query.select
            chain.insert = insert_query.insert
            chain.update = update_query.update
            return chain
        elif name == "messages":
            return msg_query
        return MagicMock()

    mock_db.table = table_router
    return mock_db, update_query


@pytest.mark.asyncio
async def test_no_existing_conversation_creates_new():
    """When no active conversation exists, create a new one."""
    db, _ = _mock_db(conversation_data=[])

    result = await get_or_create_conversation(db, ORG_ID, CHANNEL, THREAD_ID)
    assert result["id"] == "new-conv"


@pytest.mark.asyncio
async def test_recent_conversation_is_reused():
    """A conversation with a recent message should be reused."""
    recent = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    existing = {"id": "conv-existing", "status": "active"}
    db, _ = _mock_db(conversation_data=[existing], last_message_time=recent)

    result = await get_or_create_conversation(db, ORG_ID, CHANNEL, THREAD_ID)
    assert result["id"] == "conv-existing"


@pytest.mark.asyncio
async def test_stale_conversation_is_closed_and_new_created():
    """A conversation idle for >30 min should be closed; a new one created."""
    stale = (datetime.now(UTC) - timedelta(minutes=45)).isoformat()
    existing = {"id": "conv-stale", "status": "active"}
    db, update_mock = _mock_db(conversation_data=[existing], last_message_time=stale)

    result = await get_or_create_conversation(db, ORG_ID, CHANNEL, THREAD_ID)
    assert result["id"] == "new-conv"
    # Verify the old conversation was closed
    update_mock.update.assert_called_once_with({"status": "archived"})
