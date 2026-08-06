from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jordan_claw.tools.history import (
    MESSAGE_MAX_CHARS,
    read_past_conversation,
    search_past_conversations,
)


def _ctx():
    ctx = MagicMock()
    ctx.deps.org_id = "org-1"
    ctx.deps.agent_slug = "claw-main"
    ctx.deps.supabase_client = MagicMock()
    return ctx


@pytest.mark.asyncio
async def test_search_requires_query_or_date():
    result = await search_past_conversations(_ctx())
    assert "Provide a search query" in result


@pytest.mark.asyncio
async def test_search_rejects_bad_dates():
    result = await search_past_conversations(_ctx(), query="x", from_date="last tuesday")
    assert "ISO format" in result


@pytest.mark.asyncio
async def test_search_formats_excerpts_and_points_at_read_tool():
    long_tail = "z" * 400
    rows = [
        {
            "content": f"we compared sandbag loads {long_tail}",
            "role": "user",
            "created_at": "2026-08-01T10:15:00+00:00",
            "conversation_id": "c1",
        }
    ]
    with patch(
        "jordan_claw.tools.history.search_archived_messages",
        AsyncMock(return_value=rows),
    ) as mock_search:
        result = await search_past_conversations(_ctx(), query="sandbag")
    assert "c1" in result
    assert "sandbag" in result
    assert long_tail not in result  # excerpt-bounded, never the full message
    assert "read_past_conversation" in result
    assert mock_search.call_args.kwargs["agent_slug"] == "claw-main"


@pytest.mark.asyncio
async def test_search_clamps_from_date_to_30_day_cap():
    with patch(
        "jordan_claw.tools.history.search_archived_messages",
        AsyncMock(return_value=[]),
    ) as mock_search:
        await search_past_conversations(_ctx(), query="x", from_date="2020-01-01")
    from datetime import UTC, datetime, timedelta

    window_start = datetime.fromisoformat(mock_search.call_args.kwargs["window_start"])
    assert datetime.now(UTC) - window_start <= timedelta(days=31)


@pytest.mark.asyncio
async def test_search_date_only_lists_conversations_with_openers():
    convs = [{"id": "c9", "created_at": "2026-08-04T09:00:00+00:00"}]
    msgs = [
        {"conversation_id": "c9", "role": "assistant", "created_at": "t1", "content": "hi"},
        {"conversation_id": "c9", "role": "user", "created_at": "t2", "content": "plan my week"},
    ]
    with (
        patch(
            "jordan_claw.tools.history.list_recallable_conversations",
            AsyncMock(return_value=convs),
        ),
        patch(
            "jordan_claw.tools.history.get_messages_for_conversations",
            AsyncMock(return_value=msgs),
        ),
    ):
        result = await search_past_conversations(_ctx(), from_date="2026-08-04")
    assert "c9" in result
    assert "plan my week" in result  # first USER message is the opener


@pytest.mark.asyncio
async def test_search_no_matches():
    with patch(
        "jordan_claw.tools.history.search_archived_messages",
        AsyncMock(return_value=[]),
    ):
        result = await search_past_conversations(_ctx(), query="unicorn")
    assert "No archived messages matched" in result


@pytest.mark.asyncio
async def test_read_unknown_conversation():
    with patch(
        "jordan_claw.tools.history.get_recallable_conversation",
        AsyncMock(return_value=None),
    ):
        result = await read_past_conversation(_ctx(), "nope")
    assert "No archived conversation with that id" in result


@pytest.mark.asyncio
async def test_read_pages_and_truncates_messages():
    conv = {"id": "c1", "created_at": "2026-08-01T10:00:00+00:00"}
    rows = [
        {
            "role": "assistant",
            "content": "y" * (MESSAGE_MAX_CHARS + 100),
            "created_at": "2026-08-01T10:01:00+00:00",
        }
    ]
    with (
        patch(
            "jordan_claw.tools.history.get_recallable_conversation",
            AsyncMock(return_value=conv),
        ),
        patch(
            "jordan_claw.tools.history.get_conversation_messages_page",
            AsyncMock(return_value=(rows, 61)),
        ) as mock_page,
    ):
        result = await read_past_conversation(_ctx(), "c1", page=2)
    assert "page 2 of 3" in result
    assert "61 messages" in result
    assert "y" * (MESSAGE_MAX_CHARS + 100) not in result
    assert "page=3" in result  # points at the next page
    assert mock_page.call_args.kwargs["offset"] == 30


@pytest.mark.asyncio
async def test_read_page_out_of_range():
    conv = {"id": "c1", "created_at": "2026-08-01T10:00:00+00:00"}
    with (
        patch(
            "jordan_claw.tools.history.get_recallable_conversation",
            AsyncMock(return_value=conv),
        ),
        patch(
            "jordan_claw.tools.history.get_conversation_messages_page",
            AsyncMock(return_value=([], 61)),
        ),
    ):
        result = await read_past_conversation(_ctx(), "c1", page=9)
    assert "out of range" in result
