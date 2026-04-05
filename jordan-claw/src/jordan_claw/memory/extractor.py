from __future__ import annotations

import structlog
from aiogram import Bot
from pydantic_ai import Agent
from supabase._async.client import AsyncClient

from jordan_claw.db.memory import (
    append_events,
    archive_fact,
    get_active_facts,
    mark_context_stale,
    upsert_facts,
)
from jordan_claw.memory.models import ExtractedEvent, ExtractionResult, MemoryFact

log = structlog.get_logger()

EXTRACTION_SYSTEM_PROMPT = """\
You are a memory extraction agent. Your job is to identify facts and events \
from a conversation turn that are worth remembering long-term.

Rules:
1. Only extract facts with clear signal. Do not extract every passing mention.
2. Set category to one of: preference, decision, entity, workflow, relationship.
3. Set source to "explicit" when the user says "remember that..." or directly states \
something to remember. Set to "conversation" for facts inferred from natural dialogue. \
Set to "inferred" only for facts derived from patterns across multiple statements.
4. Set confidence between 0.0 and 1.0. Use 1.0 for explicit statements, 0.7-0.9 for \
clear conversational facts, 0.5-0.7 for inferred facts.
5. If a new fact contradicts an existing fact, set replaces_fact_id to the ID of the \
existing fact.
6. If the user corrects a previous statement, set has_corrections to true.
7. Do not extract facts that are already captured in the existing facts list.
8. For events, only capture significant decisions, completions, or feedback. Not routine \
conversation.
9. If there is nothing worth extracting, return empty lists.
"""


def create_extraction_agent() -> Agent[None, ExtractionResult]:
    """Create the memory extraction agent with structured output."""
    return Agent(
        "anthropic:claude-haiku-4-5-20251001",
        system_prompt=EXTRACTION_SYSTEM_PROMPT,
        output_type=ExtractionResult,
    )


def build_extraction_prompt(
    user_message: str,
    assistant_response: str,
    existing_facts: list[MemoryFact],
) -> str:
    """Build the user prompt for the extraction agent."""
    facts_section = "No existing facts."
    if existing_facts:
        fact_lines = [
            f"- [{f.id}] ({f.category}, confidence={f.confidence}) {f.content}"
            for f in existing_facts
        ]
        facts_section = "Existing facts:\n" + "\n".join(fact_lines)

    return f"""\
Analyze this conversation turn and extract any new facts or notable events.

## Conversation Turn

**User:** {user_message}

**Assistant:** {assistant_response}

## {facts_section}

Extract new or updated facts and events. Return empty lists if nothing is worth remembering."""


async def notify_memory_correction(
    db: AsyncClient,
    org_id: str,
    old_content: str,
    new_content: str,
    bot: Bot | None = None,
) -> None:
    """Send a proactive notification about a memory correction.

    If a Bot instance is available, deliver via Telegram immediately.
    Otherwise, insert an audit row for later delivery.
    """
    from jordan_claw.proactive.executors import format_memory_flag

    content = format_memory_flag(old_content, new_content)
    if bot:
        from jordan_claw.proactive.delivery import send_proactive_message

        await send_proactive_message(
            bot=bot,
            db=db,
            org_id=org_id,
            content=content,
            task_type="memory_flag",
            trigger="memory_flag",
        )
    else:
        from jordan_claw.db.proactive import insert_proactive_message

        await insert_proactive_message(
            db,
            org_id=org_id,
            task_type="memory_flag",
            trigger="memory_flag",
            content=content,
        )


async def extract_memory_background(
    db: AsyncClient,
    org_id: str,
    user_message: str,
    assistant_response: str,
    bot: Bot | None = None,
) -> None:
    """Fire-and-forget memory extraction from a conversation turn."""
    try:
        existing_facts = await get_active_facts(db, org_id)
        agent = create_extraction_agent()
        prompt = build_extraction_prompt(user_message, assistant_response, existing_facts)
        result = await agent.run(prompt)
        extraction = result.output

        # Handle corrections: archive old facts, pin new ones
        if extraction.has_corrections:
            for fact in extraction.facts:
                if fact.replaces_fact_id:
                    await archive_fact(db, fact.replaces_fact_id)
            # Add a correction event
            correction_events = [
                ExtractedEvent(
                    event_type="correction",
                    summary=f"User corrected: {f.content}",
                )
                for f in extraction.facts
                if f.replaces_fact_id
            ]
            extraction.events.extend(correction_events)

            # Notify about corrections via proactive messaging
            for fact in extraction.facts:
                if fact.replaces_fact_id:
                    old_fact = next(
                        (f for f in existing_facts if f.id == fact.replaces_fact_id),
                        None,
                    )
                    if old_fact:
                        await notify_memory_correction(
                            db, org_id, old_fact.content, fact.content, bot=bot
                        )

        await upsert_facts(db, org_id, extraction.facts, existing_facts)
        await append_events(db, org_id, extraction.events)
        await mark_context_stale(db, org_id)

        log.info(
            "memory_extraction_complete",
            org_id=org_id,
            facts_extracted=len(extraction.facts),
            events_extracted=len(extraction.events),
            has_corrections=extraction.has_corrections,
        )

    except Exception:
        log.exception("memory_extraction_failed", org_id=org_id)
