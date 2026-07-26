from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterable, AsyncIterator, Awaitable, Callable
from typing import Any

import structlog
from pydantic_ai import (
    AgentStreamEvent,
    FinalResultEvent,
    FunctionToolCallEvent,
    PartDeltaEvent,
    PartStartEvent,
    RunContext,
    TextPart,
    TextPartDelta,
)
from supabase._async.client import AsyncClient

from jordan_claw.analytics.types import RunKind
from jordan_claw.config import Settings
from jordan_claw.db.messages import get_message_by_channel_id
from jordan_claw.gateway.app_chat import (
    APP_CHANNEL,
    AppMessageRequest,
    replay_app_response,
)
from jordan_claw.gateway.app_chat import (
    channel_message_id as app_channel_message_id,
)
from jordan_claw.gateway.voice import (
    OriginalRunIncompleteError,
    handle_app_message,
)

log = structlog.get_logger()

StreamPayload = dict[str, Any]
StreamEmitter = Callable[[StreamPayload], Awaitable[None]]

HEARTBEAT_INTERVAL_S = 10.0

_pending_stream_tasks: set[asyncio.Task[None]] = set()

_TOOL_ACTIVITY: dict[str, str] = {
    "run_code": "Running code safely",
    "search_web": "Searching the web",
    "fetch_article": "Reading an article",
    "current_datetime": "Checking the current time",
    "check_calendar": "Checking your calendar",
    "schedule_event": "Updating your calendar",
    "recall_memory": "Checking memory",
    "forget_memory": "Updating memory",
    "search_notes": "Searching your notes",
    "read_note": "Reading a note",
    "create_source_note": "Writing a source note",
    "set_reminder": "Setting a reminder",
    "list_reminders": "Checking reminders",
    "cancel_reminder": "Canceling a reminder",
    "send_email": "Sending an email",
    "reply_to_email": "Replying to an email",
    "list_email_threads": "Checking email",
    "read_email_thread": "Reading an email thread",
    "normalize_medication": "Checking the medication name",
    "fetch_fda_label": "Checking the FDA label",
    "get_medication_profile": "Reviewing the medication profile",
    "save_medication_profile": "Updating the medication profile",
    "log_health_event": "Logging the health event",
    "amend_last_health_event": "Updating the health event",
    "get_health_events": "Reviewing health history",
    "get_last_visit_date": "Checking the last visit",
    "create_timeline_note": "Creating a timeline note",
    "get_care_profile": "Reviewing the care profile",
    "save_care_profile": "Updating the care profile",
    "save_care_document": "Saving a care document",
    "check_care_docs_current": "Checking care documents",
    "get_workout_profile": "Reviewing your workout profile",
    "get_workout_plan": "Reviewing your workout plan",
    "get_workout_logs": "Reviewing workout history",
    "log_workout": "Logging your workout",
    "amend_last_workout": "Updating your workout",
}


def _activity_for_tool(tool_name: str) -> str:
    """Return a safe, argument-free description of visible tool activity."""
    known = _TOOL_ACTIVITY.get(tool_name)
    if known is not None:
        return known
    words = tool_name.replace("_", " ").strip()
    return f"Using {words}" if words else "Working"


def build_agent_event_handler(emit: StreamEmitter):
    """Translate model events into safe app progress and final-text deltas.

    Tool arguments/results and model thinking parts are intentionally never
    emitted. Text is held until Pydantic AI marks the request as the final
    result, preventing intermediate model turns from appearing as the answer.
    """

    async def handle_events(
        _ctx: RunContext[Any],
        event_stream: AsyncIterable[AgentStreamEvent],
    ) -> None:
        pending_text: dict[int, str] = {}
        final_started = False

        async for event in event_stream:
            if isinstance(event, FunctionToolCallEvent):
                # Any text accumulated before a tool call belongs to an
                # intermediate model turn, not the final user-facing answer.
                pending_text.clear()
                final_started = False
                await emit(
                    {
                        "type": "status",
                        "message": _activity_for_tool(event.part.tool_name),
                    }
                )
                continue

            if isinstance(event, PartStartEvent) and isinstance(event.part, TextPart):
                if final_started and event.part.content:
                    await emit({"type": "delta", "text": event.part.content})
                else:
                    pending_text[event.index] = event.part.content
                continue

            if isinstance(event, FinalResultEvent):
                final_started = True
                for index in sorted(pending_text):
                    if content := pending_text[index]:
                        await emit({"type": "delta", "text": content})
                pending_text.clear()
                continue

            if isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                if final_started:
                    if event.delta.content_delta:
                        await emit({"type": "delta", "text": event.delta.content_delta})
                else:
                    pending_text[event.index] = (
                        pending_text.get(event.index, "") + event.delta.content_delta
                    )

    return handle_events


def start_app_message_stream(
    *,
    db: AsyncClient,
    settings: Settings,
    body: AppMessageRequest,
) -> AsyncIterator[bytes]:
    """Start one replay-safe app run and return its NDJSON event stream.

    The producer is held independently from the HTTP consumer so an iOS
    disconnect does not cancel an in-flight agent run after its user message
    has been persisted. A reconnect with the same idempotency key converges on
    that original run through the existing replay path.
    """
    queue: asyncio.Queue[StreamPayload | None] = asyncio.Queue()
    connected = True
    current_status = "Working"
    key = app_channel_message_id(body.agent_slug, body.idempotency_key)

    async def emit(payload: StreamPayload) -> None:
        nonlocal current_status
        if payload.get("type") == "status":
            current_status = str(payload.get("message") or "Working")
        elif payload.get("type") == "delta":
            current_status = "Writing response"
        if connected:
            await queue.put(payload)

    async def heartbeat() -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL_S)
            await emit({"type": "status", "message": current_status})

    async def produce() -> None:
        heartbeat_task = asyncio.create_task(heartbeat(), name=f"app-stream-heartbeat-{key}")
        try:
            await emit({"type": "status", "message": "Working"})
            original = await get_message_by_channel_id(db, key)
            if original is not None:
                await emit({"type": "status", "message": "Reconnecting to your response"})
                response = await replay_app_response(
                    db,
                    original,
                    fallback_slug=body.agent_slug,
                )
                reply = response.reply
                conversation_id = response.conversation_id
                agent_slug = response.agent_slug
            else:
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
                    event_stream_handler=build_agent_event_handler(emit),
                )
                reply = response.content
                conversation_id = response.conversation_id
                agent_slug = body.agent_slug

            await emit(
                {
                    "type": "complete",
                    "agent_slug": agent_slug,
                    "reply": reply,
                    "conversation_id": conversation_id,
                }
            )
        except OriginalRunIncompleteError:
            await emit(
                {
                    "type": "error",
                    "message": "The response is still running. Try again in a moment.",
                }
            )
        except Exception:
            log.exception(
                "app_message_stream_failed",
                agent_slug=body.agent_slug,
                channel_message_id=key,
            )
            await emit(
                {
                    "type": "error",
                    "message": "Couldn’t reach the gateway. Check your connection and try again.",
                }
            )
        finally:
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task
            if connected:
                await queue.put(None)

    producer = asyncio.create_task(produce(), name=f"app-message-stream-{key}")
    _pending_stream_tasks.add(producer)
    producer.add_done_callback(_pending_stream_tasks.discard)

    async def consume() -> AsyncIterator[bytes]:
        nonlocal connected
        try:
            while True:
                payload = await queue.get()
                if payload is None:
                    break
                line = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
                yield f"{line}\n".encode()
        finally:
            connected = False

    return consume()


async def drain_pending_stream_tasks() -> None:
    """Wait for in-flight app runs before closing shared clients."""
    if _pending_stream_tasks:
        await asyncio.gather(*list(_pending_stream_tasks), return_exceptions=True)
