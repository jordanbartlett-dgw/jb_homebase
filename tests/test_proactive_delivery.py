from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock()


@pytest.mark.asyncio
async def test_publish_skips_empty_content(mock_db):
    from jordan_claw.proactive.delivery import publish_proactive_message

    with patch(
        "jordan_claw.proactive.delivery.insert_proactive_message",
        new=AsyncMock(),
    ) as mock_insert:
        await publish_proactive_message(
            db=mock_db,
            org_id="org-1",
            content="",
            task_type="daily_scan",
            trigger="scheduled",
        )

    mock_insert.assert_not_awaited()


@pytest.mark.asyncio
async def test_publish_persists_app_artifact(mock_db):
    from jordan_claw.proactive.delivery import publish_proactive_message

    with (
        patch(
            "jordan_claw.proactive.delivery.was_sent_today",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "jordan_claw.proactive.delivery.insert_proactive_message",
            new=AsyncMock(),
        ) as mock_insert,
        patch(
            "jordan_claw.proactive.delivery.emitter.proactive_sent",
            new=AsyncMock(),
        ) as mock_emit,
    ):
        await publish_proactive_message(
            db=mock_db,
            org_id="org-1",
            content="Good morning!",
            task_type="morning_briefing",
            trigger="scheduled",
            schedule_id="s1",
            schedule_name="Morning briefing",
            agent_slug="claw-main",
        )

    mock_insert.assert_awaited_once_with(
        mock_db,
        org_id="org-1",
        task_type="morning_briefing",
        trigger="scheduled",
        content="Good morning!",
        schedule_id="s1",
        channel="app",
    )
    assert mock_emit.await_args.kwargs["channel"] == "app"


@pytest.mark.asyncio
async def test_publish_dedup_prevents_duplicate_artifact(mock_db):
    from jordan_claw.proactive.delivery import publish_proactive_message

    with (
        patch(
            "jordan_claw.proactive.delivery.was_sent_today",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "jordan_claw.proactive.delivery.insert_proactive_message",
            new=AsyncMock(),
        ) as mock_insert,
    ):
        await publish_proactive_message(
            db=mock_db,
            org_id="org-1",
            content="Good morning!",
            task_type="morning_briefing",
            trigger="scheduled",
            schedule_id="s1",
        )

    mock_insert.assert_not_awaited()


@pytest.mark.asyncio
async def test_reminder_dedup_uses_short_window(mock_db):
    from jordan_claw.proactive.delivery import publish_proactive_message

    mock_today = AsyncMock(return_value=True)
    mock_within = AsyncMock(return_value=False)
    with (
        patch("jordan_claw.proactive.delivery.was_sent_today", new=mock_today),
        patch("jordan_claw.proactive.delivery.was_sent_within", new=mock_within),
        patch(
            "jordan_claw.proactive.delivery.insert_proactive_message",
            new=AsyncMock(),
        ) as mock_insert,
        patch(
            "jordan_claw.proactive.delivery.emitter.proactive_sent",
            new=AsyncMock(),
        ),
    ):
        await publish_proactive_message(
            db=mock_db,
            org_id="org-1",
            content="Drink water",
            task_type="reminder",
            trigger="scheduled",
            schedule_id="r1",
        )

    mock_today.assert_not_awaited()
    mock_within.assert_awaited_once()
    mock_insert.assert_awaited_once()


@pytest.mark.asyncio
async def test_event_artifact_skips_schedule_dedup(mock_db):
    from jordan_claw.proactive.delivery import publish_proactive_message

    with (
        patch(
            "jordan_claw.proactive.delivery.was_sent_today",
            new=AsyncMock(),
        ) as mock_today,
        patch(
            "jordan_claw.proactive.delivery.was_sent_within",
            new=AsyncMock(),
        ) as mock_within,
        patch(
            "jordan_claw.proactive.delivery.insert_proactive_message",
            new=AsyncMock(),
        ) as mock_insert,
        patch(
            "jordan_claw.proactive.delivery.emitter.proactive_sent",
            new=AsyncMock(),
        ),
    ):
        await publish_proactive_message(
            db=mock_db,
            org_id="org-1",
            content="Memory updated.",
            task_type="memory_flag",
            trigger="memory_flag",
        )

    mock_today.assert_not_awaited()
    mock_within.assert_not_awaited()
    mock_insert.assert_awaited_once()
