from __future__ import annotations

from dataclasses import dataclass

import structlog
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.toolsets import FunctionToolset

from jordan_claw.agents.deps import AgentDeps
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

log = structlog.get_logger()


@dataclass(kw_only=True)
class ToolGroup(AbstractCapability[AgentDeps]):
    """A named bundle of tools an agent can be granted via DB config."""

    id: str
    description: str
    toolset: FunctionToolset[AgentDeps]
    group_instructions: str | None = None
    defer_loading: bool = False

    def get_toolset(self) -> FunctionToolset[AgentDeps]:
        return self.toolset

    def get_instructions(self) -> str | None:
        return self.group_instructions


def _toolset(*fns_and_names: tuple) -> FunctionToolset[AgentDeps]:
    """Build a FunctionToolset from (function, registered_name) tuples."""
    ts: FunctionToolset[AgentDeps] = FunctionToolset()
    for fn, name in fns_and_names:
        ts.add_function(fn, name=name)
    return ts


CAPABILITY_REGISTRY: dict[str, ToolGroup] = {
    "core": ToolGroup(
        id="core",
        description="Time and date awareness.",
        toolset=_toolset((current_datetime, "current_datetime")),
    ),
    "web": ToolGroup(
        id="web",
        description="Web search and article fetching.",
        toolset=_toolset((search_web, "search_web"), (fetch_article, "fetch_article")),
    ),
    "calendar": ToolGroup(
        id="calendar",
        description="Read and write Jordan's Fastmail calendar.",
        toolset=_toolset((check_calendar, "check_calendar"), (schedule_event, "schedule_event")),
    ),
    "memory": ToolGroup(
        id="memory",
        description="Recall and archive long-term facts about Jordan.",
        toolset=_toolset((recall_memory, "recall_memory"), (forget_memory, "forget_memory")),
    ),
    "obsidian": ToolGroup(
        id="obsidian",
        description="Search, read, and create notes in Jordan's Obsidian vault.",
        toolset=_toolset(
            (search_notes, "search_notes"),
            (read_note, "read_note"),
            (create_source_note, "create_source_note"),
        ),
    ),
    "workout": ToolGroup(
        id="workout",
        description="Training profile, plans, workout logging and history.",
        toolset=_toolset(
            (get_workout_profile_tool, "get_workout_profile"),
            (save_workout_profile, "save_workout_profile"),
            (get_workout_plan, "get_workout_plan"),
            (save_workout_plan_tool, "save_workout_plan"),
            (log_workout, "log_workout"),
            (get_recent_workouts, "get_recent_workouts"),
        ),
    ),
}


def resolve_capabilities(ids: list[str]) -> list[ToolGroup]:
    """Map capability ids to registered ToolGroups, skipping unknown ids with a warning."""
    groups: list[ToolGroup] = []
    for cid in ids:
        group = CAPABILITY_REGISTRY.get(cid)
        if group is None:
            log.warning("unknown_capability_skipped", capability_id=cid)
            continue
        groups.append(group)
    return groups
