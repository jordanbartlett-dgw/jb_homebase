from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import structlog
from supabase._async.client import AsyncClient

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.agents.factory import build_agent
from jordan_claw.analytics.types import RunKind
from jordan_claw.config import Settings
from jordan_claw.db.care import get_care_document, get_care_profile
from jordan_claw.db.meds import get_medication_profile
from jordan_claw.db.memory import get_recent_events
from jordan_claw.db.workout import get_active_plan, get_recent_workout_logs
from jordan_claw.memory.reader import load_memory_context
from jordan_claw.tools.calendar import get_calendar_events
from jordan_claw.tools.meds import DOC_TYPES, care_docs_status
from jordan_claw.utils.agent_runner import run_agent_instrumented

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

WEEKLY_FEEDBACK_REQUEST_MESSAGE = (
    "Weekly check-in: how did the agents do this week?\n\n"
    "Reply with `/feedback weekly <1-5> [optional note]`.\n\n"
    "The `weekly` keyword is what tags this rating as a weekly review. "
    "Leave it off and it lands as ad-hoc feedback."
)


async def _run_agent_prompt(
    db: AsyncClient,
    org_id: str,
    agent_slug: str,
    settings: Settings,
    prompt: str,
    *,
    schedule_name: str,
) -> str:
    """Build the agent and run a single prompt through the instrumented wrapper."""
    agent, model_name = await build_agent(db, org_id, agent_slug)
    # Locked policy: autonomous (proactive) runs never send email.
    # agentmail_* fields default to "" on AgentDeps, so the email tools
    # return their NOT_CONFIGURED string here. Structural enforcement, not
    # prompt-only. Chat runs (gateway/router.py) still get real creds.
    deps = AgentDeps(
        org_id=org_id,
        tavily_api_key=settings.tavily_api_key,
        fastmail_username=settings.fastmail_username,
        fastmail_app_password=settings.fastmail_app_password,
        supabase_client=db,
        openai_api_key=settings.openai_api_key,
    )
    result = await run_agent_instrumented(
        agent=agent,
        prompt=prompt,
        deps=deps,
        db=db,
        org_id=org_id,
        agent_slug=agent_slug,
        model=model_name,
        run_kind=RunKind.PROACTIVE,
        channel="proactive",
        schedule_name=schedule_name,
    )
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

    return await _run_agent_prompt(
        db,
        org_id,
        agent_slug,
        settings,
        prompt,
        schedule_name="morning_briefing",
    )


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

    events_text = (
        "\n".join(f"- {e.get('summary', 'Unknown')}" for e in recent_events)
        or "No notable events this week."
    )

    prompt = WEEKLY_REVIEW_PROMPT.format(
        calendar=calendar,
        memory=memory,
        events=events_text,
    )
    agent_slug = config.get("agent_slug", settings.default_agent_slug)

    return await _run_agent_prompt(
        db,
        org_id,
        agent_slug,
        settings,
        prompt,
        schedule_name="weekly_review",
    )


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


async def execute_reminder(
    db: AsyncClient,
    org_id: str,
    config: dict,
    settings: Settings,
) -> str:
    """Deliver the stored reminder text verbatim. No agent run, no LLM call."""
    return config.get("message", "")


async def execute_weekly_feedback_request(
    db: AsyncClient,
    org_id: str,
    config: dict,
    settings: Settings,
) -> str:
    """Static prompt asking Jordan to rate the week. No agent run, no LLM call."""
    return WEEKLY_FEEDBACK_REQUEST_MESSAGE


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

    return await _run_agent_prompt(
        db,
        org_id,
        agent_slug,
        settings,
        prompt,
        schedule_name="calendar_reminder",
    )


DAILY_WORKOUT_PROMPT = """\
Compose today's workout message for Jordan. Find today's session in the plan.
Include:
1. Today's session with its targets
2. One line tying it to the goal or to recent logs
3. A nutrition note only if today's load warrants one

Keep it short. If today is a rest day and there is nothing worth saying,
reply with exactly NOTHING_TO_SEND.

## Today
{today}

## Active Plan
{plan}

## Recent Logs
{logs}
"""


async def execute_daily_workout(
    db: AsyncClient,
    org_id: str,
    config: dict,
    settings: Settings,
) -> str:
    """Compose the morning workout nudge from the active plan and recent logs."""
    plan = await get_active_plan(db, org_id)
    if plan is None:
        return ""

    tz_name = config.get("timezone", "America/Chicago")
    today = datetime.now(ZoneInfo(tz_name))

    logs = await get_recent_workout_logs(db, org_id, limit=7)
    logs_text = (
        "\n".join(f"- [{log.logged_date}] {log.activity}: {log.notes or ''}" for log in logs)
        or "No logged workouts."
    )

    prompt = DAILY_WORKOUT_PROMPT.format(
        today=today.strftime("%A %Y-%m-%d"),
        plan=plan.model_dump_json(exclude={"org_id"}),
        logs=logs_text,
    )
    agent_slug = config.get("agent_slug", "workout-coach")
    content = await _run_agent_prompt(
        db, org_id, agent_slug, settings, prompt, schedule_name="daily_workout"
    )
    if "NOTHING_TO_SEND" in content:
        return ""
    return content


WEEKLY_TRAINING_REVIEW_PROMPT = """\
Compose the Sunday training review for Jordan. Compare this week's logs
against what the plan scheduled for the week.

Cover: what got done, what was missed, and one or two specific adjustments
for next week. If the same session was missed twice or more, propose moving
it to a different day instead of repeating it. Under 10 short sentences.
No motivational filler. No em dashes. Never invent workouts that are not
in the logs.

## Week
{week_start} to {week_end}

## Active Plan
{plan}

## This Week's Logs
{logs}
"""


async def execute_weekly_training_review(
    db: AsyncClient,
    org_id: str,
    config: dict,
    settings: Settings,
) -> str:
    """Sunday review: compare the week's logs against the plan via the coach.

    No plan or no logs this week short-circuits to a one-liner plus one
    question — deterministic, so a fake review can never be composed.
    """
    tz_name = config.get("timezone", "America/Chicago")
    today = datetime.now(ZoneInfo(tz_name))
    monday = (today - timedelta(days=today.weekday())).date()

    plan = await get_active_plan(db, org_id)
    if plan is None:
        return "No active training plan this week. Want me to draft one?"

    logs = await get_recent_workout_logs(db, org_id, limit=14)
    week_logs = [log for log in logs if log.logged_date >= monday.isoformat()]
    if not week_logs:
        return (
            "No workouts logged this week. "
            "Did you train without logging, or was it a full week off?"
        )

    logs_text = "\n".join(
        f"- [{log.logged_date}] {log.activity}: {log.notes or ''}" for log in week_logs
    )
    prompt = WEEKLY_TRAINING_REVIEW_PROMPT.format(
        week_start=monday.isoformat(),
        week_end=today.date().isoformat(),
        plan=plan.model_dump_json(exclude={"org_id"}),
        logs=logs_text,
    )
    agent_slug = config.get("agent_slug", "workout-coach")
    return await _run_agent_prompt(
        db, org_id, agent_slug, settings, prompt, schedule_name="weekly_training_review"
    )


def format_memory_flag(old_content: str, new_content: str) -> str:
    """Format a memory correction notification. No agent call needed."""
    return (
        f"I updated my understanding:\n"
        f"Before: {old_content}\n"
        f"Now: {new_content}\n\n"
        f"Let me know if that's wrong."
    )


_CARE_DOC_MESSAGE_LABELS = {"emergency": "emergency one-pager", "handoff": "caregiver handoff"}
_MED_CHANGE_SECTIONS = {"medications", "allergies"}


def _care_docs_reason(changed_sections: list[str]) -> str:
    """Summarize which kind of profile data drove a doc going stale."""
    reasons: list[str] = []
    if any(section in _MED_CHANGE_SECTIONS for section in changed_sections):
        reasons.append("medications changed")
    if any(section not in _MED_CHANGE_SECTIONS for section in changed_sections):
        reasons.append("care details changed")
    return ", ".join(reasons) if reasons else "care details changed"


def _care_docs_message_lines(display_name: str | None, statuses: dict[str, dict]) -> list[str]:
    """One deterministic line per non-current doc. Current docs produce nothing."""
    lines: list[str] = []
    for doc_type in DOC_TYPES:
        status = statuses[doc_type]
        if status["status"] == "current":
            continue

        label = _CARE_DOC_MESSAGE_LABELS[doc_type]
        subject = f"{display_name}'s {label}" if display_name else f"The care docs' {label}"

        if status["status"] == "never_generated":
            lines.append(f"{subject} has not been generated yet. Ask med-check to create it.")
            continue

        reason = _care_docs_reason(status["changed_sections"])
        lines.append(f"{subject} is out of date ({reason}). Ask med-check to regenerate it.")

    return lines


async def execute_care_docs_check(
    db: AsyncClient,
    org_id: str,
    config: dict,
    settings: Settings,
) -> str:
    """Weekly care-document staleness check. No agent run, no LLM call —
    reimplements the staleness comparison directly via the db layer, reusing
    care_docs_status (jordan_claw.tools.meds), the exact hash-diff logic
    check_care_docs_current uses, so proactive and on-demand reporting can
    never drift apart.

    All docs current returns "" — the sentinel dispatch_task's delivery path
    (publish_proactive_message) treats as do-not-send. Anything stale or
    never_generated composes one short line per affected doc.
    """
    care = await get_care_profile(db, org_id)
    meds_profile = await get_medication_profile(db, org_id)

    rows: dict[str, dict | None] = {}
    for doc_type in DOC_TYPES:
        rows[doc_type] = await get_care_document(db, org_id, doc_type)

    statuses = care_docs_status(care, meds_profile, rows)
    display_name = meds_profile.timeline_display_name if meds_profile else None
    lines = _care_docs_message_lines(display_name, statuses)

    return "\n".join(lines)
