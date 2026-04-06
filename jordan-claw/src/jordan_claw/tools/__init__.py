from __future__ import annotations

from pydantic_ai.toolsets import FunctionToolset

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.tools.calendar import check_calendar, schedule_event
from jordan_claw.tools.memory import forget_memory, recall_memory
from jordan_claw.tools.obsidian import create_source_note, fetch_article, read_note, search_notes
from jordan_claw.tools.time import current_datetime
from jordan_claw.tools.web_search import search_web

BASE_TOOLSET: FunctionToolset[AgentDeps] = FunctionToolset()
BASE_TOOLSET.add_function(current_datetime, name="current_datetime")
BASE_TOOLSET.add_function(search_web, name="search_web")
BASE_TOOLSET.add_function(check_calendar, name="check_calendar")
BASE_TOOLSET.add_function(schedule_event, name="schedule_event")
BASE_TOOLSET.add_function(recall_memory, name="recall_memory")
BASE_TOOLSET.add_function(forget_memory, name="forget_memory")
BASE_TOOLSET.add_function(search_notes, name="search_notes")
BASE_TOOLSET.add_function(read_note, name="read_note")
BASE_TOOLSET.add_function(create_source_note, name="create_source_note")
BASE_TOOLSET.add_function(fetch_article, name="fetch_article")

# Keep TOOL_REGISTRY for backward compatibility during migration.
# Remove once agents/factory.py no longer references it.
TOOL_REGISTRY = {name: tool.function for name, tool in BASE_TOOLSET.tools.items()}
