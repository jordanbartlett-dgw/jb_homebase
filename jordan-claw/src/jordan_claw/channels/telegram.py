from __future__ import annotations

import structlog
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from supabase._async.client import AsyncClient

from jordan_claw.gateway.models import IncomingMessage
from jordan_claw.gateway.router import handle_message

logger = structlog.get_logger()


def create_telegram_dispatcher(
    bot: Bot,
    *,
    db: AsyncClient,
    default_org_id: str,
    agent_slug: str,
    tavily_api_key: str,
    fastmail_username: str,
    fastmail_app_password: str,
    history_limit: int,
    environment: str,
) -> Dispatcher:
    """Create and configure the aiogram dispatcher with message handlers."""
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def handle_start(message: types.Message) -> None:
        await message.answer(
            "Hello! I'm your AI assistant. Send me a message and I'll do my best to help."
        )

    @dp.message()
    async def handle_text(message: types.Message) -> None:
        if not message.text:
            return

        chat_id = str(message.chat.id)
        message_id = str(message.message_id)

        incoming = IncomingMessage(
            channel="telegram",
            channel_thread_id=chat_id,
            channel_message_id=f"telegram:{message_id}",
            content=message.text,
            org_id=default_org_id,
        )

        try:
            response = await handle_message(
                incoming,
                db=db,
                agent_slug=agent_slug,
                tavily_api_key=tavily_api_key,
                fastmail_username=fastmail_username,
                fastmail_app_password=fastmail_app_password,
                history_limit=history_limit,
                environment=environment,
            )

            if response.content:
                try:
                    await message.answer(response.content, parse_mode="Markdown")
                except Exception:
                    await message.answer(response.content)

        except Exception:
            logger.exception("telegram_handler_error", chat_id=chat_id, message_id=message_id)
            await message.answer("Something went wrong. Try again.")

    return dp


async def start_polling(bot: Bot, dp: Dispatcher) -> None:
    """Start aiogram long-polling. Runs until cancelled."""
    logger.info("telegram_polling_started")
    try:
        await dp.start_polling(bot)
    finally:
        logger.info("telegram_polling_stopped")
