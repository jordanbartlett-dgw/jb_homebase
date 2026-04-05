from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


def _mock_db(data: list[dict] | None = None) -> MagicMock:
    """Build a mock Supabase AsyncClient that returns given data."""
    db = MagicMock()
    result = MagicMock()
    result.data = data or []

    chain = MagicMock()
    chain.execute = AsyncMock(return_value=result)
    chain.eq.return_value = chain
    chain.select.return_value = chain
    chain.limit.return_value = chain
    chain.gte.return_value = chain
    chain.lte.return_value = chain
    chain.order.return_value = chain
    chain.insert.return_value = chain
    chain.update.return_value = chain
    db.table.return_value = chain

    return db


@pytest.mark.asyncio
async def test_get_enabled_schedules():
    from jordan_claw.db.proactive import get_enabled_schedules

    rows = [
        {
            "id": "s1",
            "org_id": "org-1",
            "name": "morning_briefing",
            "cron_expression": "0 7 * * *",
            "timezone": "America/Chicago",
            "enabled": True,
            "task_type": "morning_briefing",
            "config": {"agent_slug": "claw-main"},
            "last_run_at": None,
            "created_at": "2026-04-05T00:00:00+00:00",
        }
    ]
    db = _mock_db(rows)
    schedules = await get_enabled_schedules(db)
    assert len(schedules) == 1
    assert schedules[0].name == "morning_briefing"


@pytest.mark.asyncio
async def test_update_last_run():
    from jordan_claw.db.proactive import update_last_run

    db = MagicMock()
    chain = MagicMock()
    chain.execute = AsyncMock(return_value=MagicMock())
    chain.eq.return_value = chain
    db.table.return_value = MagicMock(update=MagicMock(return_value=chain))

    await update_last_run(db, "s1")
    db.table.assert_called_with("proactive_schedules")


@pytest.mark.asyncio
async def test_insert_proactive_message():
    from jordan_claw.db.proactive import insert_proactive_message

    db = MagicMock()
    chain = MagicMock()
    chain.execute = AsyncMock(return_value=MagicMock())
    db.table.return_value = MagicMock(insert=MagicMock(return_value=chain))

    await insert_proactive_message(
        db,
        org_id="org-1",
        task_type="morning_briefing",
        trigger="scheduled",
        content="Good morning!",
        schedule_id="s1",
    )
    db.table.assert_called_with("proactive_messages")


@pytest.mark.asyncio
async def test_was_sent_today_returns_true():
    from jordan_claw.db.proactive import was_sent_today

    db = _mock_db([{"id": "msg-1"}])
    result = await was_sent_today(db, "s1", "America/Chicago")
    assert result is True


@pytest.mark.asyncio
async def test_was_sent_today_returns_false():
    from jordan_claw.db.proactive import was_sent_today

    db = _mock_db([])
    result = await was_sent_today(db, "s1", "America/Chicago")
    assert result is False


@pytest.mark.asyncio
async def test_get_telegram_chat_id():
    from jordan_claw.db.proactive import get_telegram_chat_id

    db = _mock_db([{"telegram_chat_id": 12345}])
    chat_id = await get_telegram_chat_id(db, "org-1")
    assert chat_id == 12345


@pytest.mark.asyncio
async def test_get_telegram_chat_id_not_set():
    from jordan_claw.db.proactive import get_telegram_chat_id

    db = _mock_db([{"telegram_chat_id": None}])
    chat_id = await get_telegram_chat_id(db, "org-1")
    assert chat_id is None


@pytest.mark.asyncio
async def test_save_telegram_chat_id():
    from jordan_claw.db.proactive import save_telegram_chat_id

    db = MagicMock()
    chain = MagicMock()
    chain.execute = AsyncMock(return_value=MagicMock())
    chain.eq.return_value = chain
    db.table.return_value = MagicMock(update=MagicMock(return_value=chain))

    await save_telegram_chat_id(db, "org-1", 12345)
    db.table.assert_called_with("organizations")
