from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ProactiveSchedule(BaseModel):
    """A row from the proactive_schedules table."""

    id: str
    org_id: str
    name: str
    cron_expression: str
    timezone: str
    enabled: bool
    task_type: str
    config: dict
    last_run_at: datetime | None = None
    created_at: str
