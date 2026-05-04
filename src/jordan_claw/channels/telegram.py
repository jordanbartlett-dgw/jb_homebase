from __future__ import annotations

import asyncio

import structlog
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from supabase._async.client import AsyncClient

from jordan_claw.analytics import emitter
from jordan_claw.db.conversations import most_recent_conversation_id
from jordan_claw.db.feedback import save_feedback
from jordan_claw.db.proactive import save_telegram_chat_id
from jordan_claw.db.usage_events import most_recent_agent
from jordan_claw.gateway.models import IncomingMessage
from jordan_claw.gateway.router import handle_message

logger = structlog.get_logger()


def _parse_feedback_args(text: str) -> tuple[int, str | None, str] | None:
    """Parse '/feedback [weekly] <1-5> [note]'.

    Returns (rating, note, prompt_source) on success, None on bad input.
    """
    parts = text.split(maxsplit=1)
    remainder = parts[1].strip() if len(parts) > 1 else ""

    prompt_source = "manual"
    head = remainder.split(maxsplit=1)
    if head and head[0].lower() == "weekly":
        prompt_source = "weekly_review"
        remainder = head[1].strip() if len(head) > 1 else ""

    rating_split = remainder.split(maxsplit=1)
    if not rating_split or not rating_split[0].isdigit():
        return None
    rating = int(rating_split[0])
    if not 1 <= rating <= 5:
        return None
    note = rating_split[1].strip() if len(rating_split) > 1 else None
    return rating, note, prompt_source


async def handle_feedback_command(
    message: types.Message,
    *,
    db: AsyncClient,
    default_org_id: str,
    default_agent_slug: str,
) -> None:
    """Handle /feedback. Persists rating + emits PostHog event."""
    parsed = _parse_feedback_args(message.text or "")
    if parsed is None:
        await message.answer("Usage: /feedback [weekly] <1-5> [note]")
        return
    rating, note, prompt_source = parsed

    slug = await most_recent_agent(db, org_id=default_org_id, channel="telegram")
    slug = slug or default_agent_slug
    conv_id = await most_recent_conversation_id(
        db, org_id=default_org_id, channel="telegram"
    )

    await save_feedback(
        db,
        org_id=default_org_id,
        agent_slug=slug,
        conversation_id=conv_id,
        rating=rating,
        note=note,
        prompt_source=prompt_source,
    )
    await emitter.feedback_submitted(
        org_id=default_org_id,
        user_id=None,
        agent_slug=slug,
        rating=rating,
        has_note=note is not None,
        prompt_source=prompt_source,
        conversation_id=conv_id,
    )
    await message.answer(f"Got it. Rated {rating}/5.")


def create_telegram_dispatcher(
    bot: Bot,
    *,
    db: AsyncClient,
    default_org_id: str,
    agent_slug: str,
    tavily_api_key: str,
    fastmail_username: str,
    fastmail_app_password: str,
    openai_api_key: str,
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

    @dp.message(Command("feedback"))
    async def handle_feedback(message: types.Message) -> None:
        try:
            await handle_feedback_command(
                message,
                db=db,
                default_org_id=default_org_id,
                default_agent_slug=agent_slug,
            )
        except Exception:
            logger.exception(
                "telegram_feedback_error",
                chat_id=str(message.chat.id),
                message_id=str(message.message_id),
            )
            await message.answer("Couldn't save that. Try again.")

    @dp.message()
    async def handle_text(message: types.Message) -> None:
        if not message.text:
            return

        chat_id = str(message.chat.id)
        message_id = str(message.message_id)

        # Persist Telegram chat ID for proactive messaging (fire-and-forget)
        asyncio.create_task(
            save_telegram_chat_id(db, default_org_id, message.chat.id),
            name=f"save-chat-id-{message.chat.id}",
        )

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
                openai_api_key=openai_api_key,
                history_limit=history_limit,
                environment=environment,
                bot=bot,
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
