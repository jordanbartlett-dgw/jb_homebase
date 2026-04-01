from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


def get_current_datetime() -> str:
    """Get the current date and time in US Central time."""
    now = datetime.now(ZoneInfo("America/Chicago"))
    return now.strftime("%Y-%m-%d %H:%M:%S %Z (%A)")
