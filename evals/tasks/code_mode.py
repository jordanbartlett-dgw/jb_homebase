"""CodeMode dataset: can the model compose tool results inside a `run_code`
sandbox instead of calling tools directly?

Stub toolset (4 tools, docstrings cloned from the real functions — same
routing-signal discipline as `tool_routing.py`): `get_recent_workouts`,
`get_workout_plan`, `search_notes`, `current_datetime`. The fixture workouts
are 30/45/20/60/25 minutes so cases can assert deterministic substrings (sum
180, average 36, count>=30-minutes is 3, longest-to-shortest is
60/45/30/25/20) without an LLM judge.

With `code_mode` granted, the model sees exactly one tool: `run_code` (see
`tests/test_capabilities.py::test_code_mode_replaces_tools_with_run_code`).
Tools invoked *inside* the sandbox (e.g. `get_recent_workouts`) go through the
sandbox's own `ToolManager` (`pydantic_ai_harness.code_mode._toolset
.CodeModeToolset.call_tool` -> `tool_manager.handle_call`), a *different*
`ToolManager` than the agent's top-level one.

INNER-SPAN ANSWER (verified via the 2-case live trial, cases
`sum_last_5_durations` + `what_time_is_it`, see task-25-report.md): despite
going through a separate ToolManager, inner sandboxed tool calls DO emit
their own `gen_ai.tool.name` spans, nested under the `run_code` span —
confirmed two ways: (1) `MaxToolCalls` on the real trial run counted 3 tool
calls for a case that made 2 `run_code` calls wrapping 1
`get_recent_workouts` call; (2) an ad-hoc `ToolCorrectness(expected_tools=
["run_code"], allow_extra=False)` probe against the same case failed with
`"unexpected tools: 'get_recent_workouts' (x1), ..."`, i.e. the inner tool
name is visible to span-based evaluators just like a top-level call. Every
compute case below therefore asserts `ToolCorrectness` with `allow_extra=True`
against BOTH `run_code` and the specific inner tool(s) the case requires
(e.g. `[run_code, get_recent_workouts]`) — this proves composition actually
happened, not just that `run_code` was invoked. `Contains` checks on the
output still carry the weight of proving the sandboxed computation was
correct (span presence proves the tool ran, not that its result was used
right).
"""

from __future__ import annotations

import json

from pydantic_ai import Agent
from pydantic_ai.toolsets import FunctionToolset
from pydantic_ai_harness import CodeMode

from evals.types import CodeModeInputs
from jordan_claw.agents.capabilities import CAPABILITY_REGISTRY
from jordan_claw.tools import obsidian as obsidian_tools
from jordan_claw.tools import time as time_tools
from jordan_claw.tools import workout as workout_tools

TARGET_MODEL = "anthropic:claude-sonnet-5"  # prod org default_model, pinned

INSTRUCTIONS = (
    "You are Jordan's workout coach. Use your tools to answer, writing code for any computation."
)

# 5 fixture workouts, durations 30/45/20/60/25 minutes (deliberately not sorted
# by duration) — sum 180, average 36, 3 are >= 30 minutes, longest-to-shortest
# is 60/45/30/25/20.
_RECENT_WORKOUTS_FIXTURE = (
    "- [2026-07-25] run (duration_min=30)\n"
    "- [2026-07-23] strength (duration_min=45)\n"
    "- [2026-07-21] run (duration_min=20)\n"
    "- [2026-07-19] strength (duration_min=60)\n"
    "- [2026-07-17] run (duration_min=25)"
)

_WORKOUT_PLAN_FIXTURE = json.dumps(
    {
        "id": "plan_001",
        "status": "active",
        "starts_on": "2026-07-20",
        "weeks": [
            {
                "week_number": 1,
                "focus": "Base building",
                "days": [
                    {
                        "day": "Monday",
                        "session_type": "run",
                        "description": "Easy 3mi",
                        "targets": {},
                    },
                    {
                        "day": "Wednesday",
                        "session_type": "strength",
                        "description": "Full body",
                        "targets": {},
                    },
                    {
                        "day": "Friday",
                        "session_type": "run",
                        "description": "Tempo 4mi",
                        "targets": {},
                    },
                ],
            }
        ],
        "rationale": "Build a base with steady mileage and two strength sessions per week.",
    },
    indent=2,
)

# Fixed timestamp so the negative case (case 6) has a deterministic substring
# ("2026") to assert on without touching the real clock.
_CURRENT_DATETIME_FIXTURE = "2026-07-27 09:00:00 CDT (Monday)"


def _build_toolset() -> FunctionToolset:
    """Stub the workout-domain tool surface code_mode composes over. Docstrings
    are cloned from the real functions; each stub takes plain args (no
    RunContext/AgentDeps) and returns a short, deterministic, realistic-looking
    string. What matters for this dataset is whether the model can compose
    these results correctly inside `run_code`, not what the tools themselves do."""
    ts: FunctionToolset = FunctionToolset()

    async def get_recent_workouts(limit: int = 5) -> str:
        return _RECENT_WORKOUTS_FIXTURE

    get_recent_workouts.__doc__ = workout_tools.get_recent_workouts.__doc__

    async def get_workout_plan() -> str:
        return _WORKOUT_PLAN_FIXTURE

    get_workout_plan.__doc__ = workout_tools.get_workout_plan.__doc__

    async def search_notes(
        query: str,
        note_type: str | None = None,
        tags: list[str] | None = None,
    ) -> str:
        return (
            "Found 2 matching note(s):\n\n"
            "**Base Building Block Notes** (research)\n"
            "  Tags: workout, training\n"
            "  Similarity: 0.88\n"
            "  Snippet: Notes on structuring a base-building block before...\n\n"
            "**Injury Prevention Checklist** (reference)\n"
            "  Tags: workout, health\n"
            "  Similarity: 0.79\n"
            "  Snippet: Warm-up and mobility checklist to run before...\n"
        )

    search_notes.__doc__ = obsidian_tools.search_notes.__doc__

    async def current_datetime() -> str:
        return _CURRENT_DATETIME_FIXTURE

    current_datetime.__doc__ = time_tools.current_datetime.__doc__

    for fn in (get_recent_workouts, get_workout_plan, search_notes, current_datetime):
        ts.add_function(fn, name=fn.__name__)
    return ts


async def code_mode_task(inputs: CodeModeInputs) -> str:
    agent = Agent(
        TARGET_MODEL,
        instructions=INSTRUCTIONS,
        toolsets=[_build_toolset()],
        capabilities=[
            CodeMode(
                id="code_mode",
                description=CAPABILITY_REGISTRY["code_mode"].description,
            )
        ],
    )
    result = await agent.run(inputs.user_message)
    return str(result.output)
