from __future__ import annotations

from jordan_claw.proactive.models import ProactiveSchedule


def test_schedule_from_db_row():
    row = {
        "id": "abc-123",
        "org_id": "org-456",
        "name": "morning_briefing",
        "cron_expression": "0 7 * * *",
        "timezone": "America/Chicago",
        "enabled": True,
        "task_type": "morning_briefing",
        "config": {"agent_slug": "claw-main"},
        "last_run_at": None,
        "created_at": "2026-04-05T00:00:00+00:00",
    }
    schedule = ProactiveSchedule.model_validate(row)
    assert schedule.name == "morning_briefing"
    assert schedule.config == {"agent_slug": "claw-main"}
    assert schedule.last_run_at is None


def test_schedule_with_last_run():
    row = {
        "id": "abc-123",
        "org_id": "org-456",
        "name": "weekly_review",
        "cron_expression": "0 8 * * 1",
        "timezone": "America/Chicago",
        "enabled": True,
        "task_type": "weekly_review",
        "config": {"agent_slug": "claw-main"},
        "last_run_at": "2026-04-04T08:00:00+00:00",
        "created_at": "2026-04-01T00:00:00+00:00",
    }
    schedule = ProactiveSchedule.model_validate(row)
    assert schedule.last_run_at is not None
