from __future__ import annotations

from datetime import UTC, datetime


def get_current_datetime() -> str:
    """Get the current date and time in UTC."""
    now = datetime.now(UTC)
    return now.strftime("%Y-%m-%d %H:%M:%S UTC (%A)")
