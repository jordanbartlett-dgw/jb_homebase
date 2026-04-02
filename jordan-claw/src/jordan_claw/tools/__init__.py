from __future__ import annotations

from collections.abc import Callable
from typing import Any

from jordan_claw.tools.calendar import check_calendar, schedule_event
from jordan_claw.tools.time import current_datetime
from jordan_claw.tools.web_search import search_web

TOOL_REGISTRY: dict[str, Callable[..., Any]] = {
    "current_datetime": current_datetime,
    "search_web": search_web,
    "check_calendar": check_calendar,
    "schedule_event": schedule_event,
}
