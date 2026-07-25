from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ProactiveSchedule(BaseModel):
    """A row from the proactive_schedules table.

    Exactly one of cron_expression (recurring) or run_at (one-shot) is set,
    enforced by a DB CHECK constraint (migration 016). source is 'system' for
    operator-seeded jobs, 'reminder' for rows created by the set_reminder tool.
    """

    id: str
    org_id: str
    name: str
    cron_expression: str | None = None
    run_at: datetime | None = None
    timezone: str
    enabled: bool
    task_type: str
    config: dict
    source: str = "system"
    last_run_at: datetime | None = None
    created_at: str
