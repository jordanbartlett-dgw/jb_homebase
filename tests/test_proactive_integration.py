from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jordan_claw.proactive.models import ProactiveSchedule


@pytest.mark.asyncio
async def test_full_scheduled_flow():
    """Scheduler detects a due schedule, runs the executor, sends via delivery."""
    from jordan_claw.proactive.scheduler import dispatch_task

    schedule = ProactiveSchedule(
        id="s-test",
        org_id="org-1",
        name="morning_briefing",
        cron_expression="0 7 * * *",
        timezone="America/Chicago",
        enabled=True,
        task_type="morning_briefing",
        config={"agent_slug": "claw-main"},
        last_run_at=None,
        created_at="2026-04-05T00:00:00+00:00",
    )

    mock_db = AsyncMock()
    mock_bot = AsyncMock()
    mock_bot.send_message = AsyncMock()
    mock_settings = MagicMock()
    mock_settings.fastmail_username = "user@test.com"
    mock_settings.fastmail_app_password = "test-pass"
    mock_settings.openai_api_key = "test-openai"
    mock_settings.tavily_api_key = "test-tavily"
    mock_settings.default_agent_slug = "claw-main"

    inserted_messages: list[dict] = []

    async def capture_insert(
        client,
        *,
        org_id,
        task_type,
        trigger,
        content,
        schedule_id=None,
        channel="telegram",
    ):
        inserted_messages.append(
            {
                "org_id": org_id,
                "task_type": task_type,
                "trigger": trigger,
                "content": content,
                "schedule_id": schedule_id,
            }
        )

    with (
        patch(
            "jordan_claw.proactive.executors.get_calendar_events",
            new=AsyncMock(return_value="- Standup: 09:00 - 09:30"),
        ),
        patch(
            "jordan_claw.proactive.executors.load_memory_context",
            new=AsyncMock(return_value=""),
        ),
        patch(
            "jordan_claw.proactive.executors.build_agent",
            new=AsyncMock(return_value=(MagicMock(), "test-model")),
        ),
        patch(
            "jordan_claw.proactive.executors.run_agent_instrumented",
            new=AsyncMock(return_value=SimpleNamespace(output="Good morning, Jordan!")),
        ),
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
            new_callable=AsyncMock,
            side_effect=capture_insert,
        ),
        patch(
            "jordan_claw.proactive.scheduler.update_last_run",
            new=AsyncMock(),
        ),
        patch(
            "jordan_claw.proactive.scheduler.schedule_calendar_reminders",
            new=AsyncMock(return_value=[]),
        ),
    ):
        await dispatch_task(schedule, mock_db, mock_bot, mock_settings)

    # Verify Telegram message was sent
    mock_bot.send_message.assert_called_once_with(12345, "Good morning, Jordan!")

    # Verify audit row was inserted
    assert len(inserted_messages) == 1
    assert inserted_messages[0]["task_type"] == "morning_briefing"
    assert inserted_messages[0]["trigger"] == "scheduled"
    assert inserted_messages[0]["content"] == "Good morning, Jordan!"
    assert inserted_messages[0]["schedule_id"] == "s-test"
