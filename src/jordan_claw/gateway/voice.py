from __future__ import annotations

import asyncio
import hashlib
import time
from typing import Any

import httpx
import logfire
import structlog
from pydantic import BaseModel, Field, field_validator
from supabase._async.client import AsyncClient

from jordan_claw.analytics import emitter
from jordan_claw.analytics.types import RunKind
from jordan_claw.config import Settings
from jordan_claw.db.messages import get_assistant_reply_after, get_message_by_channel_id
from jordan_claw.db.usage_events import save_usage_event
from jordan_claw.gateway.classifier import classify
from jordan_claw.gateway.models import GatewayResponse, IncomingMessage
from jordan_claw.gateway.router import handle_message
from jordan_claw.utils.agent_runner import _fire_save
from jordan_claw.utils.pricing import compute_transcription_cost

log = structlog.get_logger()

WHISPER_URL = "https://api.openai.com/v1/audio/transcriptions"
WHISPER_MODEL = "whisper-1"
TRANSCRIBE_TIMEOUT_S = 60.0
VOICE_CHANNEL = "app-voice"
IDEMPOTENCY_KEY_MAX_LEN = 120
POLL_INTERVAL_S = 2.0
POLL_TIMEOUT_S = 90.0
TRANSCRIPTION_CACHE_TTL_S = 300.0

_transcription_tasks: dict[str, asyncio.Task[str]] = {}
_transcription_cache: dict[str, tuple[float, str]] = {}
_transcription_lock = asyncio.Lock()


class TranscriptionError(Exception):
    """Whisper transcription failed.

    Message is client-safe (no provider response bodies); it becomes the
    502 detail. Provider details are logged server-side instead.
    """


class OriginalRunIncompleteError(Exception):
    """A replay was detected but the original run's reply never appeared.

    Raised after POLL_TIMEOUT_S of polling; the route maps it to a 504.
    """


class VoiceResponse(BaseModel):
    """Response body of POST /voice."""

    transcript: str
    agent_slug: str
    reply: str


class VoiceTranscriptionResponse(BaseModel):
    """Draft response from POST /voice/transcribe; no message has been sent."""

    transcript: str


class VoiceMessageRequest(BaseModel):
    """Reviewed transcript submitted by the voice preview screen."""

    transcript: str = Field(min_length=1, max_length=100_000)
    idempotency_key: str = Field(min_length=1, max_length=IDEMPOTENCY_KEY_MAX_LEN)

    @field_validator("transcript", "idempotency_key")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned


async def transcribe(
    audio: bytes,
    filename: str,
    content_type: str,
    settings: Settings,
    *,
    db: AsyncClient | None = None,
    org_id: str | None = None,
) -> str:
    """Transcribe audio bytes via the OpenAI Whisper HTTP API (raw httpx, no sdk).

    When both `db` and `org_id` are provided and transcription succeeds, this
    fires (fire-and-forget) a usage_events row and a `transcription_completed`
    PostHog event. Callers that only need a transcript (e.g. drafts) can omit
    both and no row/event is written.
    """
    with logfire.span("voice_transcribe", audio_bytes=len(audio)) as span:
        ctx = span.get_span_context()
        trace_id = f"{ctx.trace_id:032x}" if ctx and ctx.trace_id else None
        start = time.monotonic()

        try:
            async with httpx.AsyncClient(timeout=TRANSCRIBE_TIMEOUT_S) as client:
                resp = await client.post(
                    WHISPER_URL,
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                    data={"model": WHISPER_MODEL, "response_format": "verbose_json"},
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

        body = resp.json()
        text = body.get("text")
        if not isinstance(text, str):
            raise TranscriptionError("Transcription response missing text")

        raw_duration = body.get("duration")
        duration_s = raw_duration if isinstance(raw_duration, (int, float)) else None
        cost = compute_transcription_cost(duration_s) if duration_s is not None else None
        latency_ms = int((time.monotonic() - start) * 1000)

        span.set_attribute("duration_s", duration_s)
        span.set_attribute("usage.cost_usd", float(cost) if cost is not None else None)
        span.set_attribute("latency_ms", latency_ms)

        if db is not None and org_id is not None:
            _fire_save(
                save_usage_event(
                    db,
                    org_id=org_id,
                    agent_slug="whisper",
                    conversation_id=None,
                    channel=VOICE_CHANNEL,
                    run_kind=RunKind.TRANSCRIPTION,
                    schedule_name=None,
                    model=WHISPER_MODEL,
                    input_tokens=0,
                    output_tokens=0,
                    cost_usd=cost,
                    duration_ms=latency_ms,
                    tool_call_count=0,
                    success=True,
                    error_type=None,
                    error_severity=None,
                    trace_id=trace_id,
                )
            )
            await emitter.transcription_completed(
                org_id=org_id,
                duration_s=duration_s,
                audio_bytes=len(audio),
                cost_usd=cost,
                latency_ms=latency_ms,
            )

        return text


async def transcribe_once(
    audio: bytes,
    filename: str,
    content_type: str,
    settings: Settings,
    *,
    key: str,
    db: AsyncClient | None = None,
    org_id: str | None = None,
) -> str:
    """Transcribe one draft idempotently without creating a conversation row.

    Railway can replay a slow upload while Whisper is still running. Drafts
    intentionally do not touch the database, so a short process-local cache
    converges concurrent and immediately repeated requests. A restart may
    repeat the provider call, but cannot duplicate a user message or agent run.

    `db`/`org_id` pass through to `transcribe` for its usage-event/event
    bookkeeping; a cache hit makes no provider call, so it writes nothing.
    """
    now = time.monotonic()
    async with _transcription_lock:
        expired = [
            cached_key
            for cached_key, (created_at, _) in _transcription_cache.items()
            if now - created_at >= TRANSCRIPTION_CACHE_TTL_S
        ]
        for cached_key in expired:
            _transcription_cache.pop(cached_key, None)

        cached = _transcription_cache.get(key)
        if cached is not None:
            return cached[1]

        task = _transcription_tasks.get(key)
        if task is None:
            task = asyncio.create_task(
                transcribe(audio, filename, content_type, settings, db=db, org_id=org_id)
            )
            _transcription_tasks[key] = task

    try:
        transcript = await asyncio.shield(task)
    except Exception:
        async with _transcription_lock:
            if _transcription_tasks.get(key) is task:
                _transcription_tasks.pop(key, None)
        raise

    async with _transcription_lock:
        _transcription_cache[key] = (time.monotonic(), transcript)
        if _transcription_tasks.get(key) is task:
            _transcription_tasks.pop(key, None)
    return transcript


def idempotency_key(audio: bytes, header: str | None) -> str:
    """Stable dedup key for one voice utterance.

    Railway's edge replays requests that don't respond within ~20s, and
    /voice runs 30-60s, so the key must be identical across replays of the
    same request: the client-sent X-Idempotency-Key when present (stripped,
    capped at IDEMPOTENCY_KEY_MAX_LEN chars), else a hash of the audio bytes.
    """
    if header is not None:
        cleaned = header.strip()[:IDEMPOTENCY_KEY_MAX_LEN]
        if cleaned:
            return f"{VOICE_CHANNEL}-{cleaned}"
    return f"{VOICE_CHANNEL}-{hashlib.sha256(audio).hexdigest()[:32]}"


async def await_original_reply(db: AsyncClient, *, conversation_id: str, after: str) -> str:
    """Poll for the assistant reply the original run produces after `after`.

    Raises OriginalRunIncompleteError if none appears within POLL_TIMEOUT_S.
    """
    deadline = time.monotonic() + POLL_TIMEOUT_S
    while True:
        row = await get_assistant_reply_after(db, conversation_id, after)
        if row is not None:
            return row["content"]
        if time.monotonic() >= deadline:
            raise OriginalRunIncompleteError(conversation_id)
        await asyncio.sleep(POLL_INTERVAL_S)


async def replay_response(db: AsyncClient, original: dict, *, org_id: str) -> VoiceResponse:
    """Converge a detected replay onto the original run's result.

    `original` is the stored user-message row for the idempotency key. The
    transcript is its content; agent_slug comes from its metadata (persisted
    by handle_app_message). A fresh classify() is the last resort for rows
    written before metadata carried the slug — it costs a haiku call.

    Raises OriginalRunIncompleteError if the original run's reply never appears.
    """
    metadata = original.get("metadata") or {}
    agent_slug = metadata.get("agent_slug")
    if not agent_slug:
        agent_slug = await classify(db, original["content"], org_id)
    log.info(
        "voice_replay_detected",
        conversation_id=original["conversation_id"],
        agent_slug=agent_slug,
    )
    reply = await await_original_reply(
        db,
        conversation_id=original["conversation_id"],
        after=original["created_at"],
    )
    return VoiceResponse(transcript=original["content"], agent_slug=agent_slug, reply=reply)


async def handle_app_message(
    db: AsyncClient,
    *,
    org_id: str,
    agent_slug: str,
    text: str,
    settings: Settings,
    channel_message_id: str,
    channel: str = VOICE_CHANNEL,
    channel_thread_id: str | None = None,
    run_kind: RunKind = RunKind.VOICE,
    event_stream_handler: Any | None = None,
) -> GatewayResponse:
    """Run an app-originated utterance through the standard gateway flow.

    Same lifecycle as app text (conversation per channel, memory context,
    instrumented run, memory-extraction kickoff), but the reply returns over
    HTTP only — no bot delivery. channel_message_id is the stable idempotency
    key from the route, so gateway dedup fires on edge replays; agent_slug is
    persisted in the message metadata so a replay can recover the original
    route without re-classifying. Defaults are the /voice shape; /app/messages
    passes channel="app" with one thread per agent.
    """
    msg = IncomingMessage(
        channel=channel,
        channel_thread_id=channel_thread_id or channel,
        channel_message_id=channel_message_id,
        content=text,
        org_id=org_id,
        metadata={"agent_slug": agent_slug},
    )
    result = await handle_message(
        msg,
        db=db,
        agent_slug=agent_slug,
        tavily_api_key=settings.tavily_api_key,
        fastmail_username=settings.fastmail_username,
        fastmail_app_password=settings.fastmail_app_password,
        openai_api_key=settings.openai_api_key,
        agentmail_api_key=settings.agentmail_api_key,
        agentmail_inbox_id=settings.agentmail_inbox_id,
        history_limit=settings.message_history_limit,
        environment=settings.environment,
        run_kind=run_kind,
        event_stream_handler=event_stream_handler,
    )
    if result.conversation_id:
        return result

    # handle_message's dedup fired (empty-sentinel contract): the original
    # attempt persisted this key between the route's pre-check and our
    # insert. Converge on the original run's reply instead of returning
    # the empty sentinel to the client.
    log.info("voice_replay_race_window", channel_message_id=channel_message_id)
    original = await get_message_by_channel_id(db, channel_message_id)
    if original is None:
        raise OriginalRunIncompleteError(channel_message_id)
    reply = await await_original_reply(
        db,
        conversation_id=original["conversation_id"],
        after=original["created_at"],
    )
    return GatewayResponse(content=reply, conversation_id=original["conversation_id"])
