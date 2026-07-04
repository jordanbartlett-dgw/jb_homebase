from __future__ import annotations

from jordan_claw.tools.calendar import check_calendar, schedule_event
from jordan_claw.tools.memory import forget_memory, recall_memory
from jordan_claw.tools.obsidian import create_source_note, fetch_article, read_note, search_notes
from jordan_claw.tools.time import current_datetime
from jordan_claw.tools.web_search import search_web
from jordan_claw.tools.workout import (
    get_recent_workouts,
    get_workout_plan,
    get_workout_profile_tool,
    log_workout,
    save_workout_plan_tool,
    save_workout_profile,
)

__all__ = [
    "check_calendar",
    "create_source_note",
    "current_datetime",
    "fetch_article",
    "forget_memory",
    "get_recent_workouts",
    "get_workout_plan",
    "get_workout_profile_tool",
    "log_workout",
    "read_note",
    "recall_memory",
    "save_workout_plan_tool",
    "save_workout_profile",
    "schedule_event",
    "search_notes",
    "search_web",
]
