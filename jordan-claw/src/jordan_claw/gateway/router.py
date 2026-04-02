from __future__ import annotations

import time

import structlog
from supabase._async.client import AsyncClient

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.agents.factory import build_agent, db_messages_to_history
from jordan_claw.db.conversations import get_or_create_conversation, update_conversation_status
from jordan_claw.db.messages import get_recent_messages, message_exists, save_message
from jordan_claw.gateway.models import GatewayResponse, IncomingMessage
from jordan_claw.utils.token_counting import extract_usage

logger = structlog.get_logger()

ERROR_RESPONSE = "Something went wrong. Try again."


async def handle_message(
    msg: IncomingMessage,
    *,
    db: AsyncClient,
    agent_slug: str,
    tavily_api_key: str,
    fastmail_username: str,
    fastmail_app_password: str,
    history_limit: int = 50,
    environment: str = "development",
) -> GatewayResponse:
    """Process an incoming message through the full gateway lifecycle."""
    log = logger.bind(
        org_id=msg.org_id,
        channel=msg.channel,
        channel_thread_id=msg.channel_thread_id,
    )

    # 1. Dedup
    if await message_exists(db, msg.channel_message_id):
        log.info("duplicate_message_skipped", channel_message_id=msg.channel_message_id)
        return GatewayResponse(content="", conversation_id="")

    # 2. Get or create conversation
    conversation = await get_or_create_conversation(
        db, msg.org_id, msg.channel, msg.channel_thread_id
    )
    conversation_id = conversation["id"]
    log = log.bind(conversation_id=conversation_id, agent_slug=agent_slug)

    # 3. Save user message
    await save_message(
        db,
        conversation_id=conversation_id,
        role="user",
        content=msg.content,
        channel_message_id=msg.channel_message_id,
    )

    # 4. Load history
    db_messages = await get_recent_messages(db, conversation_id, limit=history_limit)

    # 5. Build agent from DB config, run with deps
    try:
        start = time.monotonic()

        agent = await build_agent(db, msg.org_id, agent_slug)
        deps = AgentDeps(
            org_id=msg.org_id,
            tavily_api_key=tavily_api_key,
            fastmail_username=fastmail_username,
            fastmail_app_password=fastmail_app_password,
        )
        history = db_messages_to_history(db_messages)

        result = await agent.run(msg.content, message_history=history, deps=deps)

        latency_ms = int((time.monotonic() - start) * 1000)
        response_text = result.output
        usage = extract_usage(result.usage())
        model_name = "claude-sonnet-4-20250514"

        if environment == "development":
            log.debug("agent_message_content", content=msg.content, response=response_text)

        log.info(
            "agent_run_complete",
            status="success",
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            total_tokens=usage["total_tokens"],
            model=model_name,
            latency_ms=latency_ms,
        )

    except Exception:
        log.exception("agent_run_failed", status="error")
        await update_conversation_status(db, conversation_id, "error")
        await save_message(
            db,
            conversation_id=conversation_id,
            role="assistant",
            content=ERROR_RESPONSE,
        )
        return GatewayResponse(content=ERROR_RESPONSE, conversation_id=conversation_id)

    # 6. Save assistant response
    await save_message(
        db,
        conversation_id=conversation_id,
        role="assistant",
        content=response_text,
        token_count=usage["total_tokens"],
        model=model_name,
    )

    # 7. Return
    return GatewayResponse(
        content=response_text,
        conversation_id=conversation_id,
        token_count=usage["total_tokens"],
        model=model_name,
    )
