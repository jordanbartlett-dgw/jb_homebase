from __future__ import annotations

import logfire
import structlog
from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import Agent
from supabase._async.client import AsyncClient

from jordan_claw.agents.capabilities import CAPABILITY_REGISTRY

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
        descriptions = [
            CAPABILITY_REGISTRY[cid].description
            for cid in row.get("capabilities") or []
            if cid in CAPABILITY_REGISTRY
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
            result = await agent.run(transcript)
            decision = result.output
            span.set_attribute("route.agent_slug", decision.agent_slug)
            span.set_attribute("route.confidence", decision.confidence)

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
