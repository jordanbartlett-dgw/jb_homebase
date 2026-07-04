from __future__ import annotations

from uuid import uuid4

import httpx
import structlog
from pydantic import BaseModel
from supabase._async.client import AsyncClient

from jordan_claw.analytics.types import RunKind
from jordan_claw.config import Settings
from jordan_claw.gateway.models import GatewayResponse, IncomingMessage
from jordan_claw.gateway.router import handle_message

log = structlog.get_logger()

WHISPER_URL = "https://api.openai.com/v1/audio/transcriptions"
WHISPER_MODEL = "whisper-1"
TRANSCRIBE_TIMEOUT_S = 60.0
VOICE_CHANNEL = "app-voice"


class TranscriptionError(Exception):
    """Whisper transcription failed.

    Message is client-safe (no provider response bodies); it becomes the
    502 detail. Provider details are logged server-side instead.
    """


class VoiceResponse(BaseModel):
    """Response body of POST /voice."""

    transcript: str
    agent_slug: str
    reply: str


async def transcribe(
    audio: bytes,
    filename: str,
    content_type: str,
    settings: Settings,
) -> str:
    """Transcribe audio bytes via the OpenAI Whisper HTTP API (raw httpx, no sdk)."""
    try:
        async with httpx.AsyncClient(timeout=TRANSCRIBE_TIMEOUT_S) as client:
            resp = await client.post(
                WHISPER_URL,
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                data={"model": WHISPER_MODEL},
                files={"file": (filename, audio, content_type)},
            )
    except httpx.HTTPError as exc:
        log.warning("transcription_request_failed", error=str(exc))
        raise TranscriptionError("Transcription request failed") from exc

    if resp.status_code != 200:
        log.warning(
            "transcription_failed",
            status_code=resp.status_code,
            body=resp.text[:500],
        )
        raise TranscriptionError(f"Transcription failed (HTTP {resp.status_code})")

    text = resp.json().get("text")
    if not isinstance(text, str):
        raise TranscriptionError("Transcription response missing text")
    return text


async def handle_app_message(
    db: AsyncClient,
    *,
    org_id: str,
    agent_slug: str,
    text: str,
    settings: Settings,
) -> GatewayResponse:
    """Run an app-originated utterance through the standard gateway flow.

    Same lifecycle as Telegram (conversation per channel, memory context,
    instrumented run, memory-extraction kickoff), but the reply returns over
    HTTP only — no bot delivery. Voice has no channel message id, so a uuid
    stands in and dedup never fires.
    """
    msg = IncomingMessage(
        channel=VOICE_CHANNEL,
        channel_thread_id=VOICE_CHANNEL,
        channel_message_id=f"{VOICE_CHANNEL}-{uuid4()}",
        content=text,
        org_id=org_id,
    )
    return await handle_message(
        msg,
        db=db,
        agent_slug=agent_slug,
        tavily_api_key=settings.tavily_api_key,
        fastmail_username=settings.fastmail_username,
        fastmail_app_password=settings.fastmail_app_password,
        openai_api_key=settings.openai_api_key,
        history_limit=settings.message_history_limit,
        environment=settings.environment,
        run_kind=RunKind.VOICE,
        bot=None,
    )
