from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from jordan_claw.gateway.app_history import (
    ConversationDetail,
    ConversationMessage,
    ConversationPage,
    ConversationSummary,
    build_summary,
)

CONVERSATION_ROW = {
    "id": "conv-1",
    "channel_thread_id": "claw-main",
    "status": "archived",
    "created_at": "2026-07-24T14:00:00+00:00",
    "updated_at": "2026-07-24T14:10:00+00:00",
}
MESSAGE_ROWS = [
    {
        "id": "msg-1",
        "conversation_id": "conv-1",
        "role": "user",
        "content": "Plan my day",
        "created_at": "2026-07-24T14:00:00+00:00",
    },
    {
        "id": "msg-2",
        "conversation_id": "conv-1",
        "role": "assistant",
        "content": "Here is the plan.",
        "created_at": "2026-07-24T14:00:30+00:00",
    },
]


def _summary() -> ConversationSummary:
    return build_summary(CONVERSATION_ROW, MESSAGE_ROWS)


def _detail() -> ConversationDetail:
    return ConversationDetail(
        conversation=_summary(),
        messages=[ConversationMessage.model_validate(row) for row in MESSAGE_ROWS],
    )


def _client() -> httpx.AsyncClient:
    from jordan_claw.main import app

    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _wire_app_state(app_token: str = "app-token") -> None:
    from jordan_claw.main import app

    settings = MagicMock()
    settings.claw_app_token = app_token
    settings.default_org_id = "org-1"
    app.state.settings = settings
    app.state.db = MagicMock()


def test_build_summary_derives_title_and_last_message_time():
    summary = build_summary(CONVERSATION_ROW, MESSAGE_ROWS)

    assert summary.id == "conv-1"
    assert summary.agent_slug == "claw-main"
    assert summary.title == "Plan my day"
    assert summary.message_count == 2
    assert summary.last_message_at.isoformat() == "2026-07-24T14:00:30+00:00"


def test_build_summary_truncates_long_first_prompt():
    rows = [{**MESSAGE_ROWS[0], "content": "word " * 30}]

    summary = build_summary(CONVERSATION_ROW, rows)

    assert len(summary.title) <= 72
    assert summary.title.endswith("…")


async def test_history_list_is_authenticated_and_passes_pagination():
    from jordan_claw import main

    _wire_app_state()
    page = ConversationPage(conversations=[_summary()], next_before="2026-07-20T00:00:00Z")

    with patch.object(main, "list_app_history", new=AsyncMock(return_value=page)) as loader:
        async with _client() as client:
            response = await client.get(
                "/app/conversations",
                params={"agent_slug": "claw-main", "limit": 10},
                headers={"Authorization": "Bearer app-token"},
            )

    assert response.status_code == 200
    assert response.json()["conversations"][0]["title"] == "Plan my day"
    assert response.json()["next_before"] == "2026-07-20T00:00:00Z"
    assert loader.await_args.kwargs["org_id"] == "org-1"
    assert loader.await_args.kwargs["agent_slug"] == "claw-main"
    assert loader.await_args.kwargs["limit"] == 10


async def test_history_service_batches_messages_for_the_page():
    from jordan_claw.gateway import app_history

    second_conversation = {
        **CONVERSATION_ROW,
        "id": "conv-2",
        "channel_thread_id": "workout-coach",
    }
    second_message = {
        **MESSAGE_ROWS[0],
        "id": "msg-3",
        "conversation_id": "conv-2",
        "content": "Plan tomorrow's run",
    }

    with (
        patch.object(
            app_history,
            "list_channel_conversations",
            new=AsyncMock(
                return_value=(
                    [CONVERSATION_ROW, second_conversation],
                    "2026-07-20T00:00:00Z",
                )
            ),
        ),
        patch.object(
            app_history,
            "get_messages_for_conversations",
            new=AsyncMock(return_value=[*MESSAGE_ROWS, second_message]),
        ) as messages_query,
    ):
        page = await app_history.list_app_history(
            MagicMock(),
            org_id="org-1",
            limit=20,
            before=None,
            agent_slug=None,
        )

    messages_query.assert_awaited_once()
    assert messages_query.await_args.args[1] == ["conv-1", "conv-2"]
    assert [conversation.title for conversation in page.conversations] == [
        "Plan my day",
        "Plan tomorrow's run",
    ]


async def test_history_rejects_bad_auth():
    _wire_app_state()

    async with _client() as client:
        response = await client.get(
            "/app/conversations",
            headers={"Authorization": "Bearer wrong"},
        )

    assert response.status_code == 401


async def test_current_conversation_returns_nullable_transcript():
    from jordan_claw import main

    _wire_app_state()
    with patch.object(
        main,
        "get_current_app_conversation",
        new=AsyncMock(return_value=None),
    ) as loader:
        async with _client() as client:
            response = await client.get(
                "/app/conversations/current",
                params={"agent_slug": "workout-coach"},
                headers={"Authorization": "Bearer app-token"},
            )

    assert response.status_code == 200
    assert response.json() is None
    assert loader.await_args.kwargs["agent_slug"] == "workout-coach"


async def test_history_detail_returns_404_outside_org_scope():
    from jordan_claw import main

    _wire_app_state()
    with patch.object(main, "get_app_history_detail", new=AsyncMock(return_value=None)):
        async with _client() as client:
            response = await client.get(
                "/app/conversations/not-mine",
                headers={"Authorization": "Bearer app-token"},
            )

    assert response.status_code == 404


async def test_history_detail_returns_messages():
    from jordan_claw import main

    _wire_app_state()
    with patch.object(main, "get_app_history_detail", new=AsyncMock(return_value=_detail())):
        async with _client() as client:
            response = await client.get(
                "/app/conversations/conv-1",
                headers={"Authorization": "Bearer app-token"},
            )

    assert response.status_code == 200
    assert [message["role"] for message in response.json()["messages"]] == [
        "user",
        "assistant",
    ]


async def test_new_chat_archives_only_the_selected_agent_thread():
    from jordan_claw import main

    _wire_app_state()
    with patch.object(
        main,
        "archive_active_conversation",
        new=AsyncMock(return_value="conv-1"),
    ) as archive:
        async with _client() as client:
            response = await client.post(
                "/app/conversations/new",
                json={"agent_slug": "claw-main"},
                headers={"Authorization": "Bearer app-token"},
            )

    assert response.status_code == 200
    assert response.json() == {"archived_conversation_id": "conv-1"}
    assert archive.await_args.kwargs == {
        "org_id": "org-1",
        "channel": "app",
        "channel_thread_id": "claw-main",
    }
