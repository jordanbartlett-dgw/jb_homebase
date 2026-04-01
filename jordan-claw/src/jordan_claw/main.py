from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import structlog
from aiogram import Bot
from fastapi import FastAPI

from jordan_claw.channels.telegram import create_telegram_dispatcher, start_polling
from jordan_claw.config import get_settings
from jordan_claw.db.client import close_supabase_client, get_supabase_client


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
    configure_logging(settings.environment, settings.log_level)
    logger = structlog.get_logger()

    # Initialize Supabase client
    db = await get_supabase_client(settings.supabase_url, settings.supabase_service_key)
    logger.info("supabase_client_initialized")

    # Initialize Telegram bot and dispatcher
    bot = Bot(token=settings.telegram_bot_token)
    dp = create_telegram_dispatcher(
        bot,
        db=db,
        default_org_id=settings.default_org_id,
        tavily_api_key=settings.tavily_api_key,
        history_limit=settings.message_history_limit,
        environment=settings.environment,
    )

    # Start Telegram polling as background task
    polling_task = asyncio.create_task(start_polling(bot, dp))
    logger.info("application_started", environment=settings.environment)

    yield

    # Shutdown
    polling_task.cancel()
    try:
        await polling_task
    except asyncio.CancelledError:
        pass
    await bot.session.close()
    await close_supabase_client()
    logger.info("application_stopped")


app = FastAPI(title="Jordan Claw", lifespan=lifespan)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
