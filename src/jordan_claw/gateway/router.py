from __future__ import annotations

import asyncio

import structlog
from supabase._async.client import AsyncClient

from jordan_claw.agents.deps import AgentDeps
from jordan_claw.agents.factory import create_agent, db_messages_to_history
from jordan_claw.analytics.types import RunKind
from jordan_claw.db.agents import get_agent_config
from jordan_claw.db.conversations import get_or_create_conversation, update_conversation_status
from jordan_claw.db.messages import get_recent_messages, message_exists, save_message
from jordan_claw.gateway.models import GatewayResponse, IncomingMessage
from jordan_claw.memory.extractor import extract_memory_background
from jordan_claw.memory.reader import load_memory_context
from jordan_claw.utils.agent_runner import run_agent_instrumented

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
    openai_api_key: str = "",
    agentmail_api_key: str = "",
    agentmail_inbox_id: str = "",
    history_limit: int = 50,
    environment: str = "development",
    run_kind: RunKind = RunKind.USER_MESSAGE,
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

    # 2. Conversation, memory context, and agent config are independent
    # reads — fetch them concurrently to cut round-trips before the LLM call.
    conversation, memory_context, agent_config = await asyncio.gather(
        get_or_create_conversation(
            db, msg.org_id, msg.channel, msg.channel_thread_id, agent_slug=agent_slug
        ),
        load_memory_context(db, msg.org_id),
        get_agent_config(db, msg.org_id, agent_slug),
        return_exceptions=True,
    )
    if isinstance(conversation, BaseException):
        raise conversation
    conversation_id = conversation["id"]
    log = log.bind(conversation_id=conversation_id, agent_slug=agent_slug)

    # Memory context falls back to empty if the memory DB fails
    if isinstance(memory_context, BaseException):
        log.warning("memory_context_load_failed", org_id=msg.org_id)
        memory_context = ""

    # 3. Save user message and load prior history concurrently. The current
    # message is filtered out of history below (the prompt already carries it),
    # so the insert-vs-select race doesn't matter.
    _, db_messages = await asyncio.gather(
        save_message(
            db,
            conversation_id=conversation_id,
            role="user",
            content=msg.content,
            channel_message_id=msg.channel_message_id,
            metadata=msg.metadata,
        ),
        get_recent_messages(db, conversation_id, limit=history_limit),
    )
    db_messages = [m for m in db_messages if m.get("channel_message_id") != msg.channel_message_id]

    # 4. Build agent from DB config, run with deps via instrumented wrapper
    try:
        if isinstance(agent_config, BaseException):
            raise agent_config
        agent, model_name = create_agent(agent_config, memory_context=memory_context)
        deps = AgentDeps(
            org_id=msg.org_id,
            tavily_api_key=tavily_api_key,
            fastmail_username=fastmail_username,
            fastmail_app_password=fastmail_app_password,
            supabase_client=db,
            openai_api_key=openai_api_key,
            agentmail_api_key=agentmail_api_key,
            agentmail_inbox_id=agentmail_inbox_id,
        )
        history = db_messages_to_history(db_messages)

        result = await run_agent_instrumented(
            agent=agent,
            prompt=msg.content,
            deps=deps,
            db=db,
            org_id=msg.org_id,
            agent_slug=agent_slug,
            model=model_name,
            run_kind=run_kind,
            channel=msg.channel,
            conversation_id=conversation_id,
            message_history=history,
        )
        response_text = result.output

        if environment == "development":
            log.debug("agent_message_content", content=msg.content, response=response_text)

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

    # 5. Save assistant response
    await save_message(
        db,
        conversation_id=conversation_id,
        role="assistant",
        content=response_text,
        token_count=result.total_tokens,
        model=model_name,
        cost_usd=float(result.cost_usd) if result.cost_usd is not None else None,
    )

    # 6. Fire-and-forget memory extraction
    asyncio.create_task(
        extract_memory_background(db, msg.org_id, msg.content, response_text),
        name=f"memory-extract-{msg.org_id}",
    )

    # 7. Return
    return GatewayResponse(
        content=response_text,
        conversation_id=conversation_id,
        token_count=result.total_tokens,
        model=model_name,
    )
