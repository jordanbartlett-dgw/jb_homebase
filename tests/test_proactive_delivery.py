from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def mock_bot() -> AsyncMock:
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    return bot


@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock()


@pytest.mark.asyncio
async def test_send_skips_empty_content(mock_bot, mock_db):
    from jordan_claw.proactive.delivery import send_proactive_message

    await send_proactive_message(
        bot=mock_bot,
        db=mock_db,
        org_id="org-1",
        content="",
        task_type="daily_scan",
        trigger="scheduled",
    )

    mock_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_send_delivers_via_telegram(mock_bot, mock_db):
    from jordan_claw.proactive.delivery import send_proactive_message

    with (
        patch(
            "jordan_claw.proactive.delivery.get_telegram_chat_id",
            new=AsyncMock(return_value=12345),
        ),
        patch(
            "jordan_claw.proactive.delivery.was_sent_today",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "jordan_claw.proactive.delivery.insert_proactive_message",
            new=AsyncMock(),
        ),
    ):
        await send_proactive_message(
            bot=mock_bot,
            db=mock_db,
            org_id="org-1",
            content="Good morning!",
            task_type="morning_briefing",
            trigger="scheduled",
            schedule_id="s1",
        )

    mock_bot.send_message.assert_called_once_with(12345, "Good morning!")


@pytest.mark.asyncio
async def test_send_skips_if_no_chat_id(mock_bot, mock_db):
    from jordan_claw.proactive.delivery import send_proactive_message

    with patch(
        "jordan_claw.proactive.delivery.get_telegram_chat_id",
        new=AsyncMock(return_value=None),
    ):
        await send_proactive_message(
            bot=mock_bot,
            db=mock_db,
            org_id="org-1",
            content="Hello!",
            task_type="morning_briefing",
            trigger="scheduled",
        )

    mock_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_send_dedup_prevents_double_send(mock_bot, mock_db):
    from jordan_claw.proactive.delivery import send_proactive_message

    with (
        patch(
            "jordan_claw.proactive.delivery.get_telegram_chat_id",
            new=AsyncMock(return_value=12345),
        ),
        patch(
            "jordan_claw.proactive.delivery.was_sent_today",
            new=AsyncMock(return_value=True),
        ),
    ):
        await send_proactive_message(
            bot=mock_bot,
            db=mock_db,
            org_id="org-1",
            content="Good morning!",
            task_type="morning_briefing",
            trigger="scheduled",
            schedule_id="s1",
        )

    mock_bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_send_event_triggered_skips_dedup(mock_bot, mock_db):
    """Event-triggered messages (no schedule_id) skip dedup check."""
    from jordan_claw.proactive.delivery import send_proactive_message

    with (
        patch(
            "jordan_claw.proactive.delivery.get_telegram_chat_id",
            new=AsyncMock(return_value=12345),
        ),
        patch(
            "jordan_claw.proactive.delivery.insert_proactive_message",
            new=AsyncMock(),
        ),
    ):
        await send_proactive_message(
            bot=mock_bot,
            db=mock_db,
            org_id="org-1",
            content="Memory updated: X → Y",
            task_type="memory_flag",
            trigger="memory_flag",
            schedule_id=None,
        )

    mock_bot.send_message.assert_called_once()
