from __future__ import annotations

import structlog
from pydantic import BaseModel, Field, field_validator
from supabase._async.client import AsyncClient

from jordan_claw.gateway import voice

log = structlog.get_logger()

APP_CHANNEL = "app"
IDEMPOTENCY_KEY_MAX_LEN = 120


class AppMessageRequest(BaseModel):
    """Body of POST /app/messages.

    agent_slug is explicit (the app's agent picker chooses it) — no classifier
    hop like /voice. idempotency_key is one client-generated UUID per message
    so Railway edge replays converge instead of double-running the agent.
    """

    text: str = Field(min_length=1, max_length=8000)
    agent_slug: str = Field(min_length=1, max_length=64)
    idempotency_key: str = Field(max_length=IDEMPOTENCY_KEY_MAX_LEN)

    @field_validator("idempotency_key")
    @classmethod
    def strip_and_require(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("idempotency_key must not be blank")
        return cleaned


class AppMessageResponse(BaseModel):
    """Response body of POST /app/messages."""

    agent_slug: str
    reply: str
    conversation_id: str


def channel_message_id(agent_slug: str, idempotency_key: str) -> str:
    """Globally unique dedup key: app channel + agent thread + client key."""
    cleaned = idempotency_key.strip()[:IDEMPOTENCY_KEY_MAX_LEN]
    return f"{APP_CHANNEL}-{agent_slug}-{cleaned}"


async def replay_app_response(
    db: AsyncClient, original: dict, *, fallback_slug: str
) -> AppMessageResponse:
    """Converge a detected replay onto the original run's reply.

    `original` is the stored user-message row for the dedup key. agent_slug
    comes from its metadata (persisted by handle_app_message); fallback_slug
    covers rows missing it. Raises OriginalRunIncompleteError if the original
    run's reply never appears.
    """
    metadata = original.get("metadata") or {}
    agent_slug = metadata.get("agent_slug") or fallback_slug
    log.info(
        "app_message_replay_detected",
        conversation_id=original["conversation_id"],
        agent_slug=agent_slug,
    )
    reply = await voice.await_original_reply(
        db,
        conversation_id=original["conversation_id"],
        after=original["created_at"],
    )
    return AppMessageResponse(
        agent_slug=agent_slug,
        reply=reply,
        conversation_id=original["conversation_id"],
    )
