from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from jordan_claw.db.conversations import (
    get_recallable_conversation,
    list_recallable_conversations,
)
from jordan_claw.db.messages import (
    get_conversation_messages_page,
    search_archived_messages,
)

WINDOW_START = "2026-07-07T00:00:00+00:00"


def _chain(rows, count=None):
    """Mock supabase query chain: every builder method returns the chain."""
    q = MagicMock()
    for m in ("select", "eq", "gte", "lte", "in_", "ilike", "order", "limit", "range"):
        getattr(q, m).return_value = q
    q.execute = AsyncMock(return_value=MagicMock(data=rows, count=count))
    return q


def _client(q):
    db = MagicMock()
    db.table.return_value = q
    return db


@pytest.mark.asyncio
async def test_search_scopes_to_own_archived_app_thread():
    row = {
        "content": "we discussed sandbag squats",
        "role": "user",
        "created_at": "2026-08-01T10:00:00+00:00",
        "conversation_id": "c1",
    }
    q = _chain([row])
    rows = await search_archived_messages(
        _client(q),
        org_id="org-1",
        agent_slug="workout-coach",
        query="sandbag",
        window_start=WINDOW_START,
    )
    assert rows == [row]
    q.eq.assert_any_call("conversations.org_id", "org-1")
    q.eq.assert_any_call("conversations.channel", "app")
    q.eq.assert_any_call("conversations.channel_thread_id", "workout-coach")
    q.eq.assert_any_call("conversations.status", "archived")
    q.gte.assert_any_call("conversations.created_at", WINDOW_START)
    q.in_.assert_any_call("role", ["user", "assistant"])
    q.ilike.assert_any_call("content", "%sandbag%")
    q.lte.assert_not_called()


@pytest.mark.asyncio
async def test_search_applies_window_end_when_given():
    q = _chain([])
    await search_archived_messages(
        _client(q),
        org_id="org-1",
        agent_slug="claw-main",
        query="x",
        window_start=WINDOW_START,
        window_end="2026-08-02T00:00:00+00:00",
    )
    q.lte.assert_any_call("conversations.created_at", "2026-08-02T00:00:00+00:00")


@pytest.mark.asyncio
async def test_list_recallable_scopes_and_orders_newest_first():
    q = _chain([{"id": "c1", "created_at": "2026-08-01T10:00:00+00:00"}])
    rows = await list_recallable_conversations(
        _client(q),
        org_id="org-1",
        agent_slug="claw-main",
        window_start=WINDOW_START,
    )
    assert rows[0]["id"] == "c1"
    q.eq.assert_any_call("channel_thread_id", "claw-main")
    q.eq.assert_any_call("status", "archived")
    q.gte.assert_any_call("created_at", WINDOW_START)
    q.order.assert_any_call("created_at", desc=True)


@pytest.mark.asyncio
async def test_get_recallable_conversation_returns_none_when_absent():
    q = _chain([])
    row = await get_recallable_conversation(
        _client(q),
        conversation_id="nope",
        org_id="org-1",
        agent_slug="claw-main",
        window_start=WINDOW_START,
    )
    assert row is None
    q.eq.assert_any_call("id", "nope")
    q.eq.assert_any_call("status", "archived")


@pytest.mark.asyncio
async def test_messages_page_returns_rows_and_exact_total():
    q = _chain([{"role": "user", "content": "a", "created_at": "t"}], count=61)
    rows, total = await get_conversation_messages_page(_client(q), "c1", offset=30, limit=30)
    assert (len(rows), total) == (1, 61)
    q.range.assert_called_once_with(30, 59)
    q.order.assert_any_call("created_at", desc=False)
