from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
from contextlib import asynccontextmanager

import logfire
import structlog
from aiogram import Bot
from fastapi import FastAPI, HTTPException, Request

from jordan_claw.analytics import emitter
from jordan_claw.analytics.posthog_client import shutdown_posthog
from jordan_claw.channels.telegram import create_telegram_dispatcher, start_polling
from jordan_claw.config import get_settings
from jordan_claw.db.client import close_supabase_client, get_supabase_client
from jordan_claw.db.messages import get_message_by_channel_id
from jordan_claw.events.pipeline import process_event
from jordan_claw.gateway.analytics_proxy import build_analytics_router
from jordan_claw.gateway.classifier import classify
from jordan_claw.gateway.voice import (
    OriginalRunIncompleteError,
    TranscriptionError,
    VoiceResponse,
    handle_app_message,
    idempotency_key,
    replay_response,
    transcribe,
)
from jordan_claw.proactive.scheduler import scheduler_loop


def configure_logging(environment: str, log_level: str) -> None:
    """Configure structlog with console (dev) or JSON (prod) rendering."""
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # Configure Logfire before structlog so traces are active from the start
    if settings.logfire_token:
        logfire.configure(
            token=settings.logfire_token,
            service_name="jordan-claw",
            environment=settings.environment,
        )
        logfire.instrument_fastapi(app)
        logfire.instrument_httpx()
        logfire.instrument_pydantic_ai()

    configure_logging(settings.environment, settings.log_level)
    logger = structlog.get_logger()

    if settings.logfire_token:
        logger.info("logfire_configured", environment=settings.environment)

    # Initialize Supabase client
    db = await get_supabase_client(settings.supabase_url, settings.supabase_service_key)
    logger.info("supabase_client_initialized")

    # Initialize Telegram bot and dispatcher
    bot = Bot(token=settings.telegram_bot_token)
    dp = create_telegram_dispatcher(
        bot,
        db=db,
        default_org_id=settings.default_org_id,
        agent_slug=settings.default_agent_slug,
        tavily_api_key=settings.tavily_api_key,
        fastmail_username=settings.fastmail_username,
        fastmail_app_password=settings.fastmail_app_password,
        openai_api_key=settings.openai_api_key,
        history_limit=settings.message_history_limit,
        environment=settings.environment,
    )

    # Start Telegram polling as background task
    polling_tasks = [asyncio.create_task(start_polling(bot, dp))]

    # Scheduler invariant: bots must always contain default_agent_slug
    bots: dict[str, Bot] = {settings.default_agent_slug: bot}

    # Optional second bot: the workout coach
    workout_bot: Bot | None = None
    if settings.workout_telegram_bot_token:
        workout_bot = Bot(token=settings.workout_telegram_bot_token)
        workout_dp = create_telegram_dispatcher(
            workout_bot,
            db=db,
            default_org_id=settings.default_org_id,
            agent_slug=settings.workout_agent_slug,
            tavily_api_key=settings.tavily_api_key,
            fastmail_username=settings.fastmail_username,
            fastmail_app_password=settings.fastmail_app_password,
            openai_api_key=settings.openai_api_key,
            history_limit=settings.message_history_limit,
            environment=settings.environment,
        )
        bots[settings.workout_agent_slug] = workout_bot
        polling_tasks.append(asyncio.create_task(start_polling(workout_bot, workout_dp)))
        logger.info("workout_bot_started", agent_slug=settings.workout_agent_slug)

    # Start proactive messaging scheduler
    scheduler_task = asyncio.create_task(
        scheduler_loop(db, bots, settings),
        name="proactive-scheduler",
    )
    logger.info("proactive_scheduler_started")

    # Expose shared state for request handlers (webhook route)
    app.state.settings = settings
    app.state.db = db
    app.state.bots = bots

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
    for task in polling_tasks:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    scheduler_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await scheduler_task
    await emitter.drain_pending_emits()
    shutdown_posthog()
    await bot.session.close()
    if workout_bot is not None:
        await workout_bot.session.close()
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
async def health_check():
    return {"status": "ok"}


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
            bots=request.app.state.bots,
        ),
        name=f"event-{source}",
    )
    _pending_event_tasks.add(task)
    task.add_done_callback(_pending_event_tasks.discard)
    return {"accepted": True}


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
    settings = request.app.state.settings
    if not settings.claw_app_token:
        # Unconfigured token means the surface is disabled, never open.
        raise HTTPException(status_code=503, detail="voice surface disabled")

    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    # bytes comparison: the str form of compare_digest raises on non-ASCII input
    if scheme.lower() != "bearer" or not secrets.compare_digest(
        token.encode(), settings.claw_app_token.encode()
    ):
        raise HTTPException(status_code=401)

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
            transcript = await transcribe(audio, filename, content_type, settings)
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
