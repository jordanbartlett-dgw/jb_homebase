from __future__ import annotations

import logfire
import structlog
from supabase._async.client import AsyncClient

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.agents.factory import build_agent
from jordan_claw.analytics import emitter
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
    # Locked policy: autonomous (event-triggered) runs never send email.
    # agentmail_* fields default to "" on AgentDeps, so the email tools
    # return their NOT_CONFIGURED string here. Structural enforcement, not
    # prompt-only. Chat runs (gateway/router.py) still get real creds.
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
        await emitter.event_trigger_fired(
            org_id=trigger.org_id,
            user_id=None,
            trigger_name=trigger.name,
            source=trigger.source,
            outcome="nothing_to_send",
            cost_usd=result.cost_usd,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            duration_ms=result.duration_ms,
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
    await emitter.event_trigger_fired(
        org_id=trigger.org_id,
        user_id=None,
        trigger_name=trigger.name,
        source=trigger.source,
        outcome="fired",
        cost_usd=result.cost_usd,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        duration_ms=result.duration_ms,
    )


async def process_event(
    db: AsyncClient,
    *,
    source: str,
    payload: dict,
    settings: Settings,
) -> int:
    """Run every enabled trigger for source against the payload. Returns runs started."""
    with logfire.span("event.process", source=source) as span:
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

        span.set_attribute("triggers", len(triggers))
        span.set_attribute("started", started)
        log.info("event.processed", source=source, triggers=len(triggers), started=started)
        return started
