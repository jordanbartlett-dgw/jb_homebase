from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime

import logfire
import structlog
from anthropic import AsyncAnthropic
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic_evals.evaluators import EvaluatorContext
from pydantic_evals.evaluators.llm_as_a_judge import set_default_judge_model
from pydantic_evals.online import configure as configure_online_evals
from pydantic_evals.online import wait_for_evaluations

from jordan_claw.analytics import emitter
from jordan_claw.analytics.posthog_client import shutdown_posthog
from jordan_claw.analytics.types import RunKind
from jordan_claw.config import Settings, get_settings
from jordan_claw.db.client import close_supabase_client, get_supabase_client
from jordan_claw.db.conversations import archive_active_conversation
from jordan_claw.db.messages import get_message_by_channel_id
from jordan_claw.events.pipeline import process_event
from jordan_claw.gateway.analytics_proxy import build_analytics_router
from jordan_claw.gateway.app_chat import (
    APP_CHANNEL,
    AppMessageRequest,
    AppMessageResponse,
    replay_app_response,
)
from jordan_claw.gateway.app_chat import (
    channel_message_id as app_channel_message_id,
)
from jordan_claw.gateway.app_feedback import (
    FeedbackRecordError,
    FeedbackRequest,
    record_app_feedback,
)
from jordan_claw.gateway.app_history import (
    ConversationDetail,
    ConversationPage,
    NewConversationRequest,
    NewConversationResponse,
    get_app_history_detail,
    get_current_app_conversation,
    list_app_history,
)
from jordan_claw.gateway.app_stream import (
    drain_pending_stream_tasks,
    start_app_message_stream,
)
from jordan_claw.gateway.app_today import TodayResponse, load_today
from jordan_claw.gateway.classifier import classify
from jordan_claw.gateway.voice import (
    OriginalRunIncompleteError,
    TranscriptionError,
    VoiceMessageRequest,
    VoiceResponse,
    VoiceTranscriptionResponse,
    handle_app_message,
    idempotency_key,
    replay_response,
    transcribe,
    transcribe_once,
)
from jordan_claw.health import build_health_report
from jordan_claw.proactive.scheduler import scheduler_loop
from jordan_claw.utils.agent_runner import drain_pending_writes

log = structlog.get_logger()


def configure_logging(environment: str, log_level: str, *, logfire_enabled: bool = False) -> None:
    """Configure structlog with console (dev) or JSON (prod) rendering.

    When `logfire_enabled`, every structlog event is also forwarded to Logfire
    (correlated with the active trace/span) via `logfire.integrations.structlog.
    LogfireProcessor`, exported as `logfire.StructlogProcessor`. `console_log=False`
    (its default) keeps the bridge additive: Logfire does its own stdout export,
    so the processor must not also print to console, or lines double up next to
    our existing JSON/console renderer.
    """
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if logfire_enabled:
        shared_processors.append(logfire.StructlogProcessor(console_log=False))

    if environment == "production":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, log_level.upper(), logging.INFO),
    )


def _log_dropped_online_eval(ctx: EvaluatorContext) -> None:
    """Default `on_max_concurrency` handler: an evaluator was dropped instead
    of run because the process-wide concurrency limit was hit. Silent by
    default in pydantic-evals; log it so a saturated online-eval pipeline is
    visible rather than quietly under-sampling production traffic.
    """
    log.warning("online_eval_dropped_max_concurrency")


def configure_eval_defaults(settings: Settings) -> None:
    """Wire pydantic-evals' online judge model and sampling defaults.

    `default_sample_rate` gates judge-sampled online evals (0 = off, the
    Settings default); deterministic per-evaluator checks run regardless,
    pinned at 1.0 at the evaluator level. `sampling_mode="correlated"` keeps
    a run's online-eval decisions consistent across evaluators within that
    run rather than flipping a coin per evaluator.
    """
    set_default_judge_model(settings.eval_judge_model)
    configure_online_evals(
        default_sample_rate=settings.online_eval_sample_rate,
        sampling_mode="correlated",
        metadata={"service": "jordan-claw"},
        on_max_concurrency=_log_dropped_online_eval,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # Configure Logfire before structlog so traces are active from the start
    if settings.logfire_token:
        logfire.configure(
            token=settings.logfire_token,
            service_name="jordan-claw",
            environment=settings.environment,
            scrubbing=logfire.ScrubbingOptions(
                # Structured-attribute patterns only; gen_ai message content is
                # governed by include_content per agent, not scrubbing.
                extra_patterns=["date_of_birth", "dob", "app_password"],
            ),
        )
        logfire.instrument_fastapi(app)
        logfire.instrument_httpx()
        logfire.instrument_pydantic_ai()

    configure_logging(
        settings.environment,
        settings.log_level,
        logfire_enabled=bool(settings.logfire_token),
    )
    logger = structlog.get_logger()

    if settings.logfire_token:
        logger.info("logfire_configured", environment=settings.environment)

    configure_eval_defaults(settings)

    # Initialize Supabase client
    db = await get_supabase_client(settings.supabase_url, settings.supabase_service_key)
    logger.info("supabase_client_initialized")

    # Start the app-only proactive scheduler. Generated artifacts are persisted
    # for app surfaces; no outbound channel process runs in this service.
    scheduler_task = asyncio.create_task(
        scheduler_loop(db, settings),
        name="proactive-scheduler",
    )
    logger.info("proactive_scheduler_started")

    # Expose shared state for request handlers.
    app.state.settings = settings
    app.state.db = db
    app.state.anthropic = AsyncAnthropic(api_key=settings.anthropic_api_key)

    # Mount analytics proxy after settings are loaded so org_id/token are available
    app.include_router(
        build_analytics_router(
            token=settings.frontend_analytics_token,
            org_id=settings.default_org_id,
        )
    )

    logger.info("application_started", environment=settings.environment)

    yield

    # Shutdown
    scheduler_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await scheduler_task
    # Streams can spawn usage writes, so drain them first.
    await drain_pending_stream_tasks()
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(wait_for_evaluations(), timeout=5)
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(drain_pending_writes(), timeout=5)
    await emitter.drain_pending_emits()
    shutdown_posthog()
    await app.state.anthropic.close()
    await close_supabase_client()
    logger.info("application_stopped")


app = FastAPI(title="Jordan Claw", lifespan=lifespan)

# Keep strong references to fire-and-forget event tasks (same pattern as
# agent_runner._fire_save) so they aren't garbage-collected mid-run.
_pending_event_tasks: set[asyncio.Task] = set()


async def drain_pending_event_tasks() -> None:
    """Wait for in-flight webhook event tasks. Used by tests for deterministic asserts."""
    if _pending_event_tasks:
        await asyncio.gather(*list(_pending_event_tasks), return_exceptions=True)


@app.get("/health")
async def health_check(request: Request):
    """Config-aware health: every active DB agent must resolve to a served model."""
    report = await build_health_report(
        request.app.state.db,
        anthropic_client=request.app.state.anthropic,
    )
    payload = report.model_dump()
    if report.status != "ok":
        return JSONResponse(status_code=503, content=payload)
    return payload


@app.post("/webhooks/{source}", status_code=202)
async def receive_webhook(source: str, request: Request):
    settings = request.app.state.settings
    if not settings.claw_webhook_secret:
        # Unconfigured secret means the surface is disabled, never open.
        raise HTTPException(status_code=503, detail="webhook surface disabled")

    provided = request.headers.get("X-Claw-Secret", "")
    # bytes comparison: the str form of compare_digest raises on non-ASCII input
    if not secrets.compare_digest(provided.encode(), settings.claw_webhook_secret.encode()):
        raise HTTPException(status_code=401)

    payload = await request.json()
    task = asyncio.create_task(
        process_event(
            request.app.state.db,
            source=source,
            payload=payload,
            settings=settings,
        ),
        name=f"event-{source}",
    )
    _pending_event_tasks.add(task)
    task.add_done_callback(_pending_event_tasks.discard)
    return {"accepted": True}


def _require_app_token(request: Request, *, surface: str) -> None:
    """Bearer auth against CLAW_APP_TOKEN for every app-facing surface."""
    settings = request.app.state.settings
    if not settings.claw_app_token:
        # Unconfigured token means the surface is disabled, never open.
        raise HTTPException(status_code=503, detail=f"{surface} surface disabled")

    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    # bytes comparison: the str form of compare_digest raises on non-ASCII input
    if scheme.lower() != "bearer" or not secrets.compare_digest(
        token.encode(), settings.claw_app_token.encode()
    ):
        raise HTTPException(status_code=401)


@app.post("/app/messages", response_model=AppMessageResponse)
async def app_text_message(body: AppMessageRequest, request: Request) -> AppMessageResponse:
    """Text chat from the JB Homebase app: explicit agent, replay-safe, blocking reply.

    The app's agent picker makes the slug explicit, so there is no classifier
    hop. One gateway conversation per agent (channel="app", thread=slug)
    matches the app's thread-per-agent UI. The client sends one UUID
    idempotency_key per message; Railway edge replays converge on the
    original run's reply exactly like /voice.
    """
    _require_app_token(request, surface="app messages")
    settings = request.app.state.settings
    db = request.app.state.db
    key = app_channel_message_id(body.agent_slug, body.idempotency_key)

    try:
        original = await get_message_by_channel_id(db, key)
        if original is not None:
            return await replay_app_response(db, original, fallback_slug=body.agent_slug)

        response = await handle_app_message(
            db,
            org_id=settings.default_org_id,
            agent_slug=body.agent_slug,
            text=body.text,
            settings=settings,
            channel_message_id=key,
            channel=APP_CHANNEL,
            channel_thread_id=body.agent_slug,
            run_kind=RunKind.USER_MESSAGE,
        )
    except OriginalRunIncompleteError as exc:
        raise HTTPException(status_code=504, detail="original request did not complete") from exc

    return AppMessageResponse(
        agent_slug=body.agent_slug,
        reply=response.content,
        conversation_id=response.conversation_id,
        traceparent=response.traceparent,
    )


@app.post("/app/messages/stream")
async def app_text_message_stream(
    body: AppMessageRequest,
    request: Request,
) -> StreamingResponse:
    """Stream safe progress plus the final text reply as newline-delimited JSON.

    Tool names are translated to argument-free activity labels. Private model
    thinking, tool arguments, and tool results are never part of this contract.
    The completed reply follows the same persistence and replay lifecycle as
    POST /app/messages.
    """
    _require_app_token(request, surface="app message stream")
    events = start_app_message_stream(
        db=request.app.state.db,
        settings=request.app.state.settings,
        body=body,
    )
    return StreamingResponse(
        events,
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/app/conversations", response_model=ConversationPage)
async def app_conversations(
    request: Request,
    agent_slug: str | None = Query(default=None, min_length=1, max_length=64),
    before: datetime | None = None,
    limit: int = Query(default=20, ge=1, le=50),
) -> ConversationPage:
    """List app conversations for History, newest session first."""
    _require_app_token(request, surface="app conversations")
    return await list_app_history(
        request.app.state.db,
        org_id=request.app.state.settings.default_org_id,
        limit=limit,
        before=before,
        agent_slug=agent_slug,
    )


@app.get("/app/conversations/current", response_model=ConversationDetail | None)
async def app_current_conversation(
    request: Request,
    agent_slug: str = Query(min_length=1, max_length=64),
) -> ConversationDetail | None:
    """Return the active transcript for an agent so app relaunches hydrate."""
    _require_app_token(request, surface="app conversations")
    return await get_current_app_conversation(
        request.app.state.db,
        org_id=request.app.state.settings.default_org_id,
        agent_slug=agent_slug,
    )


@app.post("/app/conversations/new", response_model=NewConversationResponse)
async def app_new_conversation(
    body: NewConversationRequest,
    request: Request,
) -> NewConversationResponse:
    """Archive an agent's active app session; the next send starts clean."""
    _require_app_token(request, surface="app conversations")
    archived_id = await archive_active_conversation(
        request.app.state.db,
        org_id=request.app.state.settings.default_org_id,
        channel=APP_CHANNEL,
        channel_thread_id=body.agent_slug,
    )
    return NewConversationResponse(archived_conversation_id=archived_id)


@app.post("/app/feedback", status_code=202)
async def app_feedback(body: FeedbackRequest, request: Request) -> dict[str, str]:
    """Attach user feedback (thumbs up/down, rating, note) to a run's trace."""
    _require_app_token(request, surface="app feedback")
    settings = request.app.state.settings
    if not settings.logfire_token:
        raise HTTPException(status_code=503, detail="feedback surface disabled")

    try:
        await record_app_feedback(settings, body)
    except FeedbackRecordError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {"status": "recorded"}


@app.get("/app/conversations/{conversation_id}", response_model=ConversationDetail)
async def app_conversation_detail(
    conversation_id: str,
    request: Request,
) -> ConversationDetail:
    """Return an org-scoped, read-only app transcript."""
    _require_app_token(request, surface="app conversations")
    detail = await get_app_history_detail(
        request.app.state.db,
        org_id=request.app.state.settings.default_org_id,
        conversation_id=conversation_id,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return detail


@app.get("/app/today", response_model=TodayResponse)
async def app_today(
    request: Request,
    days: int = Query(default=7, ge=1, le=30),
) -> TodayResponse:
    """Return today's existing briefing and a structured upcoming agenda."""
    _require_app_token(request, surface="app today")
    settings = request.app.state.settings
    return await load_today(
        request.app.state.db,
        org_id=settings.default_org_id,
        fastmail_username=settings.fastmail_username,
        fastmail_app_password=settings.fastmail_app_password,
        days=days,
    )


@app.post("/voice", response_model=VoiceResponse)
async def voice_message(request: Request) -> VoiceResponse:
    """Voice ingestion: whisper transcript -> classifier route -> gateway reply.

    Request: raw audio bytes as the body, filename/content-type via the
    X-Audio-Filename and Content-Type headers, bearer auth against
    CLAW_APP_TOKEN. Raw bytes instead of a multipart UploadFile because
    python-multipart is not a dependency and adding one for a single-field
    upload isn't worth it.

    Idempotency: this endpoint runs 30-60s and Railway's edge replays
    requests that don't respond within ~20s, so processing is keyed by a
    stable idempotency key. Clients (Flutter) should send one
    X-Idempotency-Key per utterance; without the header the key falls back
    to a hash of the audio bytes. A replayed request skips transcription and
    the agent run, waits for the original run's reply, and returns it.

    Response: VoiceResponse — {"transcript", "agent_slug", "reply"}.
    Transcription failure -> 502; replay whose original run never finished
    -> 504; classifier failure is invisible (falls back to claw-main by
    design).
    """
    _require_app_token(request, surface="voice")
    settings = request.app.state.settings
    db = request.app.state.db
    audio = await request.body()
    filename = request.headers.get("X-Audio-Filename", "voice.m4a")
    content_type = request.headers.get("Content-Type", "application/octet-stream")
    key = idempotency_key(audio, request.headers.get("X-Idempotency-Key"))

    try:
        # Pre-transcription dedup: an edge replay of an in-flight request
        # already persisted this key, so skip Whisper and the agent run and
        # converge on the original run's reply.
        original = await get_message_by_channel_id(db, key)
        if original is not None:
            return await replay_response(db, original, org_id=settings.default_org_id)

        try:
            transcript = await transcribe(
                audio,
                filename,
                content_type,
                settings,
                db=request.app.state.db,
                org_id=settings.default_org_id,
            )
        except TranscriptionError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        # Classifier failure is invisible by design: it falls back to claw-main.
        agent_slug = await classify(db, transcript, settings.default_org_id)
        response = await handle_app_message(
            db,
            org_id=settings.default_org_id,
            agent_slug=agent_slug,
            text=transcript,
            settings=settings,
            channel_message_id=key,
        )
    except OriginalRunIncompleteError as exc:
        raise HTTPException(status_code=504, detail="original request did not complete") from exc
    return VoiceResponse(transcript=transcript, agent_slug=agent_slug, reply=response.content)


@app.post("/voice/transcribe", response_model=VoiceTranscriptionResponse)
async def voice_transcription(request: Request) -> VoiceTranscriptionResponse:
    """Transcribe an audio draft without sending it to an agent.

    The Flutter preview-before-send flow calls this after recording stops.
    No conversation or message row is created. X-Idempotency-Key converges
    Railway edge replays onto one in-process Whisper task/result.
    """
    _require_app_token(request, surface="voice")
    settings = request.app.state.settings
    audio = await request.body()
    filename = request.headers.get("X-Audio-Filename", "voice.m4a")
    content_type = request.headers.get("Content-Type", "application/octet-stream")
    key = idempotency_key(audio, request.headers.get("X-Idempotency-Key"))

    try:
        transcript = await transcribe_once(
            audio,
            filename,
            content_type,
            settings,
            key=key,
            db=request.app.state.db,
            org_id=settings.default_org_id,
        )
    except TranscriptionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return VoiceTranscriptionResponse(transcript=transcript)


@app.post("/voice/messages", response_model=VoiceResponse)
async def voice_transcript_message(
    body: VoiceMessageRequest,
    request: Request,
) -> VoiceResponse:
    """Route a reviewed voice transcript and run its selected agent.

    This is the only step in the two-stage voice flow that persists a user
    message. The required idempotency key gives it the same replay convergence
    guarantees as the backward-compatible one-shot POST /voice endpoint.
    """
    _require_app_token(request, surface="voice")
    settings = request.app.state.settings
    db = request.app.state.db
    key = idempotency_key(body.transcript.encode(), body.idempotency_key)

    try:
        original = await get_message_by_channel_id(db, key)
        if original is not None:
            return await replay_response(db, original, org_id=settings.default_org_id)

        agent_slug = await classify(db, body.transcript, settings.default_org_id)
        response = await handle_app_message(
            db,
            org_id=settings.default_org_id,
            agent_slug=agent_slug,
            text=body.transcript,
            settings=settings,
            channel_message_id=key,
            channel=APP_CHANNEL,
            channel_thread_id=agent_slug,
        )
    except OriginalRunIncompleteError as exc:
        raise HTTPException(status_code=504, detail="original request did not complete") from exc
    return VoiceResponse(
        transcript=body.transcript,
        agent_slug=agent_slug,
        reply=response.content,
    )
