from __future__ import annotations

from collections.abc import Callable
from typing import Any

from jordan_claw.tools.calendar import check_calendar, schedule_event
from jordan_claw.tools.memory import forget_memory, recall_memory
from jordan_claw.tools.obsidian import create_source_note, fetch_article, read_note, search_notes
from jordan_claw.tools.time import current_datetime
from jordan_claw.tools.web_search import search_web

TOOL_REGISTRY: dict[str, Callable[..., Any]] = {
    "current_datetime": current_datetime,
    "search_web": search_web,
    "check_calendar": check_calendar,
    "schedule_event": schedule_event,
    "recall_memory": recall_memory,
    "forget_memory": forget_memory,
    "search_notes": search_notes,
    "read_note": read_note,
    "create_source_note": create_source_note,
    "fetch_article": fetch_article,
}
