from __future__ import annotations

import time

import logfire
import structlog
from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import Agent
from supabase._async.client import AsyncClient

from jordan_claw.agents.capabilities import CAPABILITY_REGISTRY
from jordan_claw.analytics.types import RunKind
from jordan_claw.db.usage_events import save_usage_event
from jordan_claw.utils.agent_runner import _fire_save
from jordan_claw.utils.pricing import compute_cost
from jordan_claw.utils.token_counting import extract_usage

log = structlog.get_logger()

CLASSIFIER_MODEL = "anthropic:claude-haiku-4-5-20251001"
CONFIDENCE_FLOOR = 0.6
DEFAULT_AGENT = "claw-main"


class RouteDecision(BaseModel):
    """Classifier output: which agent should handle the utterance."""

    model_config = ConfigDict(frozen=True)

    agent_slug: str
    confidence: float = Field(ge=0.0, le=1.0)


def build_classifier(agent_catalog: str) -> Agent[None, RouteDecision]:
    return Agent(
        CLASSIFIER_MODEL,
        instructions=(
            "Route the user's utterance to the single best-matching agent from the "
            "catalog below, based on each agent's capabilities. When no agent is "
            f"clearly better, choose {DEFAULT_AGENT}.\n"
            f"{agent_catalog}"
        ),
        output_type=RouteDecision,
    )


async def _agent_catalog(db: AsyncClient, org_id: str) -> tuple[str, set[str]]:
    """Build the catalog text from active agents + their capability descriptions."""
    result = (
        await db.table("agents")
        .select("slug, name, capabilities")
        .eq("org_id", org_id)
        .eq("is_active", True)
        .execute()
    )
    lines: list[str] = []
    slugs: set[str] = set()
    for row in result.data:
        slugs.add(row["slug"])
        # Config-only capabilities (e.g. private_content) have no description
        # and don't belong in a routing catalog.
        descriptions = [
            cap.description
            for cid in row.get("capabilities") or []
            if (cap := CAPABILITY_REGISTRY.get(cid)) is not None
            and isinstance(cap.description, str)
        ]
        lines.append(f"- {row['slug']} ({row['name']}): {' '.join(descriptions)}")
    return "\n".join(lines), slugs


async def classify(db: AsyncClient, transcript: str, org_id: str) -> str:
    """Route a transcript to an agent slug.

    Failure mode is always DEFAULT_AGENT, never an error to the user:
    low confidence, unknown slug, and any exception all fall back.
    """
    try:
        catalog, known_slugs = await _agent_catalog(db, org_id)
        agent = build_classifier(catalog)
        with logfire.span("voice_classify", org_id=org_id) as span:
            ctx = span.get_span_context()
            trace_id = f"{ctx.trace_id:032x}" if ctx and ctx.trace_id else None

            start = time.monotonic()
            result = await agent.run(transcript)
            duration_ms = int((time.monotonic() - start) * 1000)

            decision = result.output
            span.set_attribute("route.agent_slug", decision.agent_slug)
            span.set_attribute("route.confidence", decision.confidence)

            usage = extract_usage(result.usage)
            cost = compute_cost(
                CLASSIFIER_MODEL,
                usage["input_tokens"],
                usage["output_tokens"],
                cache_read_tokens=usage["cache_read_tokens"],
                cache_write_tokens=usage["cache_write_tokens"],
            )
            span.set_attribute("usage.input_tokens", usage["input_tokens"])
            span.set_attribute("usage.output_tokens", usage["output_tokens"])
            span.set_attribute("usage.cost_usd", float(cost) if cost is not None else None)
            span.set_attribute("usage.duration_ms", duration_ms)

            _fire_save(
                save_usage_event(
                    db,
                    org_id=org_id,
                    agent_slug="voice-classifier",
                    conversation_id=None,
                    channel="app-voice",
                    run_kind=RunKind.CLASSIFIER,
                    schedule_name=None,
                    model=CLASSIFIER_MODEL,
                    input_tokens=usage["input_tokens"],
                    output_tokens=usage["output_tokens"],
                    cost_usd=cost,
                    duration_ms=duration_ms,
                    tool_call_count=0,
                    success=True,
                    error_type=None,
                    error_severity=None,
                    trace_id=trace_id,
                    cache_read_tokens=usage["cache_read_tokens"],
                    cache_write_tokens=usage["cache_write_tokens"],
                )
            )

        if decision.confidence < CONFIDENCE_FLOOR:
            log.info(
                "voice_classify_low_confidence",
                agent_slug=decision.agent_slug,
                confidence=decision.confidence,
            )
            return DEFAULT_AGENT
        if decision.agent_slug not in known_slugs:
            log.warning("voice_classify_unknown_slug", agent_slug=decision.agent_slug)
            return DEFAULT_AGENT
        return decision.agent_slug
    except Exception:
        log.exception("voice_classify_failed")
        return DEFAULT_AGENT
