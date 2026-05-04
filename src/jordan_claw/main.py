from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

import logfire
import structlog
from aiogram import Bot
from fastapi import FastAPI

from jordan_claw.channels.telegram import create_telegram_dispatcher, start_polling
from jordan_claw.config import get_settings
from jordan_claw.db.client import close_supabase_client, get_supabase_client
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
    polling_task = asyncio.create_task(start_polling(bot, dp))

    # Start proactive messaging scheduler
    scheduler_task = asyncio.create_task(
        scheduler_loop(db, bot, settings),
        name="proactive-scheduler",
    )
    logger.info("proactive_scheduler_started")

    logger.info("application_started", environment=settings.environment)

    yield

    # Shutdown
    polling_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await polling_task
    scheduler_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await scheduler_task
    await bot.session.close()
    await close_supabase_client()
    logger.info("application_stopped")


app = FastAPI(title="Jordan Claw", lifespan=lifespan)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
