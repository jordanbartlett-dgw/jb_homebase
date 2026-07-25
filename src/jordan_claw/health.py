from __future__ import annotations

from typing import Literal

import structlog
from anthropic import AsyncAnthropic, NotFoundError
from pydantic import BaseModel
from supabase._async.client import AsyncClient

from jordan_claw.db.agents import get_org_default_model, resolve_model

log = structlog.get_logger()

# Definitive verdicts only; transient API failures are never cached so they
# retry on the next health check. Model ids are immutable once valid/invalid,
# so process-lifetime caching is safe.
_model_cache: dict[str, bool] = {}


class AgentHealth(BaseModel):
    slug: str
    model: str
    bot_running: bool
    model_ok: bool | None  # None = could not be validated (non-anthropic or API unreachable)


class HealthReport(BaseModel):
    status: Literal["ok", "degraded"]
    agents: list[AgentHealth]
    missing_bots: list[str]
    invalid_models: list[str]


async def _validate_model(client: AsyncAnthropic, model: str) -> bool | None:
    provider, _, bare = model.rpartition(":")
    if provider not in ("", "anthropic"):
        return None
    if bare in _model_cache:
        return _model_cache[bare]
    try:
        await client.models.retrieve(bare)
    except NotFoundError:
        _model_cache[bare] = False
        return False
    except Exception:
        log.warning("health.model_check_unavailable", model=bare)
        return None
    _model_cache[bare] = True
    return True


async def build_health_report(
    db: AsyncClient,
    *,
    running_bots: set[str],
    anthropic_client: AsyncAnthropic,
) -> HealthReport:
    """Cross-check every active agent in the DB against runtime reality.

    An active agent whose bot dispatcher is not running, or whose configured
    model the Anthropic API does not serve, degrades the report (503 at the
    endpoint) so Railway's deploy healthcheck fails loudly instead of the bot
    going silent.
    """
    result = (
        await db.table("agents")
        .select("slug, org_id, model, is_active")
        .eq("is_active", True)
        .execute()
    )

    agents: list[AgentHealth] = []
    missing_bots: list[str] = []
    invalid_models: list[str] = []
    org_defaults: dict[str, str | None] = {}
    for row in result.data:
        slug, org_id = row["slug"], row["org_id"]
        if org_id not in org_defaults:
            org_defaults[org_id] = await get_org_default_model(db, org_id)
        # Validate the RESOLVED model — a NULL row inherits the org default,
        # and an unresolvable model must gate the deploy like an invalid one.
        try:
            model = resolve_model(row["model"], org_defaults[org_id])
        except ValueError:
            model = "(unset)"
        bot_running = slug in running_bots
        model_ok = False if model == "(unset)" else await _validate_model(anthropic_client, model)
        if not bot_running:
            missing_bots.append(slug)
        if model_ok is False:
            invalid_models.append(slug)
        agents.append(
            AgentHealth(slug=slug, model=model, bot_running=bot_running, model_ok=model_ok)
        )

    degraded = bool(missing_bots or invalid_models)
    if degraded:
        log.warning("health.degraded", missing_bots=missing_bots, invalid_models=invalid_models)
    return HealthReport(
        status="degraded" if degraded else "ok",
        agents=agents,
        missing_bots=missing_bots,
        invalid_models=invalid_models,
    )
