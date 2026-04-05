from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import structlog
from supabase._async.client import AsyncClient

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.agents.factory import build_agent
from jordan_claw.config import Settings
from jordan_claw.db.memory import get_recent_events
from jordan_claw.memory.reader import load_memory_context
from jordan_claw.tools.calendar import get_calendar_events

log = structlog.get_logger()

MORNING_BRIEFING_PROMPT = """\
Compose a concise morning briefing for Jordan. Include:
1. Today's calendar overview (what's coming up, any prep needed)
2. Relevant context from memory

Keep it short and actionable. No fluff.

## Today's Calendar
{calendar}

## Memory Context
{memory}
"""

WEEKLY_REVIEW_PROMPT = """\
Compose a concise weekly review for Jordan. Include:
1. Overview of this week's calendar (meetings, key events)
2. What was learned this week (from memory events)
3. Any patterns or follow-ups worth noting

Keep it short and actionable.

## This Week's Calendar
{calendar}

## Memory Context
{memory}

## This Week's Activity
{events}
"""

CALENDAR_REMINDER_PROMPT = """\
Jordan has a meeting coming up in 30 minutes. Compose a short pre-meeting brief.
Include any relevant context you know about the attendees or topic.

## Meeting
{event_title} at {event_time}

## Memory Context
{memory}
"""


async def _run_agent_prompt(
    db: AsyncClient,
    org_id: str,
    agent_slug: str,
    settings: Settings,
    prompt: str,
) -> str:
    """Build the agent and run a single prompt, returning the output text."""
    agent, _ = await build_agent(db, org_id, agent_slug)
    deps = AgentDeps(
        org_id=org_id,
        tavily_api_key=settings.tavily_api_key,
        fastmail_username=settings.fastmail_username,
        fastmail_app_password=settings.fastmail_app_password,
        supabase_client=db,
        openai_api_key=settings.openai_api_key,
    )
    result = await agent.run(prompt, deps=deps)
    return result.output


async def execute_morning_briefing(
    db: AsyncClient,
    org_id: str,
    config: dict,
    settings: Settings,
) -> str:
    """Compose a morning briefing with today's calendar and memory context."""
    tz_name = config.get("timezone", "America/Chicago")
    today = datetime.now(ZoneInfo(tz_name))
    today_str = today.strftime("%Y-%m-%d")

    calendar = await get_calendar_events(
        settings.fastmail_username,
        settings.fastmail_app_password,
        today_str,
        today_str,
    )
    memory = await load_memory_context(db, org_id)

    prompt = MORNING_BRIEFING_PROMPT.format(calendar=calendar, memory=memory)
    agent_slug = config.get("agent_slug", settings.default_agent_slug)

    return await _run_agent_prompt(db, org_id, agent_slug, settings, prompt)


async def execute_weekly_review(
    db: AsyncClient,
    org_id: str,
    config: dict,
    settings: Settings,
) -> str:
    """Compose a weekly review with this week's calendar, memory, and events."""
    tz_name = config.get("timezone", "America/Chicago")
    tz = ZoneInfo(tz_name)
    today = datetime.now(tz)
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)

    calendar = await get_calendar_events(
        settings.fastmail_username,
        settings.fastmail_app_password,
        monday.strftime("%Y-%m-%d"),
        sunday.strftime("%Y-%m-%d"),
    )
    memory = await load_memory_context(db, org_id)
    recent_events = await get_recent_events(db, org_id, limit=30)

    events_text = "\n".join(
        f"- {e.get('summary', 'Unknown')}" for e in recent_events
    ) or "No notable events this week."

    prompt = WEEKLY_REVIEW_PROMPT.format(
        calendar=calendar,
        memory=memory,
        events=events_text,
    )
    agent_slug = config.get("agent_slug", settings.default_agent_slug)

    return await _run_agent_prompt(db, org_id, agent_slug, settings, prompt)


def _parse_event_times(
    events_text: str,
    tz_name: str = "America/Chicago",
) -> list[tuple[str, datetime, datetime]]:
    """Parse event lines into (title, start, end) tuples.

    Expected format: "- Title: HH:MM - HH:MM" or "- Title: All day"
    Returns empty list for unparseable lines.
    """
    tz = ZoneInfo(tz_name)
    today = datetime.now(tz).date()
    results = []

    for line in events_text.strip().split("\n"):
        match = re.match(r"^- (.+): (\d{2}:\d{2}) - (\d{2}:\d{2})", line)
        if not match:
            continue
        title = match.group(1)
        start_time = datetime.strptime(match.group(2), "%H:%M").time()
        end_time = datetime.strptime(match.group(3), "%H:%M").time()
        start = datetime.combine(today, start_time, tzinfo=tz)
        end = datetime.combine(today, end_time, tzinfo=tz)
        results.append((title, start, end))

    return results


async def execute_daily_scan(
    db: AsyncClient,
    org_id: str,
    config: dict,
    settings: Settings,
) -> str:
    """Scan today's calendar for conflicts. Returns empty string if none found."""
    tz_name = config.get("timezone", "America/Chicago")
    today = datetime.now(ZoneInfo(tz_name))
    today_str = today.strftime("%Y-%m-%d")

    events_text = await get_calendar_events(
        settings.fastmail_username,
        settings.fastmail_app_password,
        today_str,
        today_str,
    )

    if events_text == "No events scheduled.":
        return ""

    events = _parse_event_times(events_text, tz_name=tz_name)
    conflicts = []

    for i, (title_a, start_a, end_a) in enumerate(events):
        for title_b, start_b, end_b in events[i + 1 :]:
            if start_a < end_b and start_b < end_a:
                conflicts.append(f"- {title_a} and {title_b} overlap")

    if not conflicts:
        return ""

    return "Calendar conflicts detected:\n" + "\n".join(conflicts)


async def execute_calendar_reminder(
    db: AsyncClient,
    org_id: str,
    config: dict,
    settings: Settings,
    *,
    event_title: str,
    event_time: str,
) -> str:
    """Compose a pre-meeting brief for an upcoming calendar event."""
    memory = await load_memory_context(db, org_id)

    prompt = CALENDAR_REMINDER_PROMPT.format(
        event_title=event_title,
        event_time=event_time,
        memory=memory,
    )
    agent_slug = config.get("agent_slug", settings.default_agent_slug)

    return await _run_agent_prompt(db, org_id, agent_slug, settings, prompt)


def format_memory_flag(old_content: str, new_content: str) -> str:
    """Format a memory correction notification. No agent call needed."""
    return (
        f"I updated my understanding:\n"
        f"Before: {old_content}\n"
        f"Now: {new_content}\n\n"
        f"Let me know if that's wrong."
    )
