from __future__ import annotations

import structlog
from supabase._async.client import AsyncClient

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.agents.factory import build_agent
from jordan_claw.analytics.types import RunKind
from jordan_claw.config import Settings
from jordan_claw.db.event_triggers import EventTrigger, get_triggers
from jordan_claw.proactive.delivery import publish_proactive_message
from jordan_claw.utils.agent_runner import run_agent_instrumented

log = structlog.get_logger()

NOTHING_TO_SEND = "NOTHING_TO_SEND"


class SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def render_prompt(template: str, payload: dict) -> str:
    """Fill template placeholders from payload; unknown keys pass through as-is."""
    return template.format_map(SafeDict(payload))


async def _run_trigger(
    db: AsyncClient,
    trigger: EventTrigger,
    payload: dict,
    settings: Settings,
) -> None:
    """Run one trigger's agent and persist any actionable app artifact."""
    agent, model_name = await build_agent(db, trigger.org_id, trigger.agent_slug)
    deps = AgentDeps(
        org_id=trigger.org_id,
        tavily_api_key=settings.tavily_api_key,
        fastmail_username=settings.fastmail_username,
        fastmail_app_password=settings.fastmail_app_password,
        supabase_client=db,
        openai_api_key=settings.openai_api_key,
    )
    result = await run_agent_instrumented(
        agent=agent,
        prompt=render_prompt(trigger.prompt_template, payload),
        deps=deps,
        db=db,
        org_id=trigger.org_id,
        agent_slug=trigger.agent_slug,
        model=model_name,
        run_kind=RunKind.EVENT,
        channel="webhook",
        schedule_name=trigger.name,
    )
    content = result.output

    if NOTHING_TO_SEND in content:
        log.info(
            "event.nothing_to_send",
            trigger_name=trigger.name,
            source=trigger.source,
        )
        return

    await publish_proactive_message(
        db=db,
        org_id=trigger.org_id,
        content=content,
        task_type="event_trigger",
        trigger=trigger.name,
        schedule_name=trigger.name,
        agent_slug=trigger.agent_slug,
    )


async def process_event(
    db: AsyncClient,
    *,
    source: str,
    payload: dict,
    settings: Settings,
) -> int:
    """Run every enabled trigger for source against the payload. Returns runs started."""
    triggers = await get_triggers(db, source)
    started = 0

    for trigger in triggers:
        try:
            await _run_trigger(db, trigger, payload, settings)
            started += 1
        except Exception:
            log.exception(
                "event.trigger_failed",
                trigger_name=trigger.name,
                source=source,
            )

    log.info("event.processed", source=source, triggers=len(triggers), started=started)
    return started
