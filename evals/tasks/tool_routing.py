"""Tool-routing dataset: given a single user ask, does the model call the
right claw-main tool(s)? Stub versions of the claw-main tool surface most
relevant to routing decisions (obsidian, web, calendar, memory, reminders,
workout, email), with docstrings cloned from the REAL functions — those
docstrings are the actual routing signal per repo discipline (see
`docs/architecture.md` / CLAUDE.md "Tool docstrings are the LLM's routing
signal"). Canned deterministic returns; the eval question is tool selection,
not tool output quality.

This dataset does NOT replicate claw-main's production system prompt — that
prompt is assembled at runtime across migrations 001, 015, 017, and 029 (base
prompt, reminders, cross-agent reads, email), with no single source literal
to copy. Instead it uses a minimal instruction good enough to route ("You are
Jordan's personal assistant. Use your tools to answer.") and leans entirely
on tool docstrings to drive selection, which is exactly the signal this
dataset is scoring.
"""

from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.toolsets import FunctionToolset

from evals.types import ToolRoutingInputs
from jordan_claw.tools import calendar as calendar_tools
from jordan_claw.tools import email as email_tools
from jordan_claw.tools import memory as memory_tools
from jordan_claw.tools import obsidian as obsidian_tools
from jordan_claw.tools import reminders as reminder_tools
from jordan_claw.tools import time as time_tools
from jordan_claw.tools import web_search as web_search_tools
from jordan_claw.tools import workout as workout_tools

TARGET_MODEL = "anthropic:claude-sonnet-5"  # prod org default_model, pinned

INSTRUCTIONS = "You are Jordan's personal assistant. Use your tools to answer."


def _build_toolset() -> FunctionToolset:
    """Stub the routing-relevant subset of claw-main's tool surface. Docstrings
    are cloned from the real functions (routing signal parity with prod) but
    each stub takes plain args — no RunContext/AgentDeps — and returns a
    short, deterministic, realistic-looking string instead of touching a real
    service. What matters for this dataset is which tool gets called, not
    what it returns."""
    ts: FunctionToolset = FunctionToolset()

    async def current_datetime() -> str:
        return "2026-07-27 09:00:00 CDT (Monday)"

    current_datetime.__doc__ = time_tools.current_datetime.__doc__

    async def search_notes(
        query: str,
        note_type: str | None = None,
        tags: list[str] | None = None,
    ) -> str:
        return (
            "Found 2 matching note(s):\n\n"
            "**Foster Greatness UK Council Scoring Framework** (research)\n"
            "  Tags: fg, uk, council\n"
            "  Similarity: 0.91\n"
            "  Snippet: Draft framework for scoring UK council Local Offers...\n\n"
            "**AgentMail Integration Notes** (project)\n"
            "  Tags: email, claw\n"
            "  Similarity: 0.85\n"
            "  Snippet: How claw-main's own agent inbox is wired up...\n"
        )

    search_notes.__doc__ = obsidian_tools.search_notes.__doc__

    async def read_note(title: str) -> str:
        return (
            "# AgentMail Integration Notes\n"
            "**Type:** project | **Tags:** email, claw\n"
            "**Links:** none\n\n"
            "Notes on how claw-main's own agent inbox (jordanb@agentmail.to) is "
            "wired up: send/reply/list/read tools, structural send policy, "
            "5-minute watcher."
        )

    read_note.__doc__ = obsidian_tools.read_note.__doc__

    async def search_web(query: str) -> str:
        return (
            "**Anthropic ships Claude Opus 5**\n"
            "Anthropic announced its newest flagship model today, citing gains "
            "in agentic coding and long-horizon reasoning.\n"
            "https://example.com/anthropic-opus-5"
        )

    search_web.__doc__ = web_search_tools.search_web.__doc__

    async def fetch_article(url: str) -> str:
        return (
            "**Source URL:** https://example.com/eval-harnesses\n\n"
            "Eval harnesses give teams a repeatable way to score agent behavior "
            "against real tool surfaces instead of eyeballing transcripts..."
        )

    fetch_article.__doc__ = obsidian_tools.fetch_article.__doc__

    async def check_calendar(start_date: str, end_date: str) -> str:
        return "- Team sync: 09:00 - 09:30\n- Dentist: 14:00 - 15:00"

    check_calendar.__doc__ = calendar_tools.check_calendar.__doc__

    async def schedule_event(
        title: str,
        start: str,
        end: str,
        location: str | None = None,
        description: str | None = None,
    ) -> str:
        return "Created: Lunch with Sarah on 2026-07-31 from 12:00 to 13:00"

    schedule_event.__doc__ = calendar_tools.schedule_event.__doc__

    async def recall_memory(query: str, category: str | None = None) -> str:
        return (
            "Found 1 memory fact(s):\n\n"
            "- [preference] Jordan prefers concise replies (confidence: 0.9)"
        )

    recall_memory.__doc__ = memory_tools.recall_memory.__doc__

    async def set_reminder(
        message: str,
        run_at: str | None = None,
        cron: str | None = None,
        agent_slug: str = "claw-main",
    ) -> str:
        return "Reminder set (id 42). Next: Tuesday 2026-07-28 09:00 CDT."

    set_reminder.__doc__ = reminder_tools.set_reminder.__doc__

    async def get_recent_workouts(limit: int = 7) -> str:
        return (
            "- [2026-07-25] run (distance_mi=5, duration_min=42)\n"
            "- [2026-07-23] strength (exercises=bench,squat)"
        )

    get_recent_workouts.__doc__ = workout_tools.get_recent_workouts.__doc__

    async def read_email_thread(thread_id: str) -> str:
        return (
            "[msg_123] from vendor@fulfillment-co.com | Order #4521 status\n"
            "<incoming_email>\n"
            "Your order shipped July 24 via UPS, tracking 1Z999AA10123456784.\n"
            "</incoming_email>"
        )

    read_email_thread.__doc__ = email_tools.read_email_thread.__doc__

    for fn in (
        current_datetime,
        search_notes,
        read_note,
        search_web,
        fetch_article,
        check_calendar,
        schedule_event,
        recall_memory,
        set_reminder,
        get_recent_workouts,
        read_email_thread,
    ):
        ts.add_function(fn, name=fn.__name__)
    return ts


async def tool_routing_task(inputs: ToolRoutingInputs) -> str:
    agent = Agent(
        TARGET_MODEL,
        instructions=INSTRUCTIONS,
        toolsets=[_build_toolset()],
    )
    result = await agent.run(inputs.user_message)
    return str(result.output)
