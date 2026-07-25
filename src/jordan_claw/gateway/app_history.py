from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from supabase._async.client import AsyncClient

from jordan_claw.db.conversations import (
    get_active_conversation,
    get_channel_conversation,
    list_channel_conversations,
)
from jordan_claw.db.messages import (
    get_conversation_messages,
    get_messages_for_conversations,
)
from jordan_claw.gateway.app_chat import APP_CHANNEL

TITLE_MAX_LENGTH = 72


class ConversationMessage(BaseModel):
    """A readable app transcript message."""

    id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


class ConversationSummary(BaseModel):
    """History-list metadata derived from an app conversation and its messages."""

    id: str
    agent_slug: str
    status: Literal["active", "archived", "error"]
    title: str
    message_count: int
    created_at: datetime
    last_message_at: datetime


class ConversationPage(BaseModel):
    """Cursor-paginated app conversation history."""

    conversations: list[ConversationSummary]
    next_before: str | None = None


class ConversationDetail(BaseModel):
    """One conversation and its read-only transcript."""

    conversation: ConversationSummary
    messages: list[ConversationMessage]


class NewConversationRequest(BaseModel):
    """Agent thread whose active conversation should be closed."""

    agent_slug: str = Field(min_length=1, max_length=64)


class NewConversationResponse(BaseModel):
    """Result of starting clean; the next send mints the new conversation."""

    archived_conversation_id: str | None


def _title(messages: list[dict]) -> str:
    first_user = next((row["content"] for row in messages if row["role"] == "user"), None)
    if not first_user:
        return "New conversation"
    normalized = " ".join(first_user.split())
    if len(normalized) <= TITLE_MAX_LENGTH:
        return normalized
    return f"{normalized[: TITLE_MAX_LENGTH - 1].rstrip()}…"


def build_summary(conversation: dict, messages: list[dict]) -> ConversationSummary:
    """Build stable UI metadata without requiring a title column migration."""
    last_message_at = messages[-1]["created_at"] if messages else conversation["created_at"]
    return ConversationSummary(
        id=conversation["id"],
        agent_slug=conversation["channel_thread_id"],
        status=conversation["status"],
        title=_title(messages),
        message_count=len(messages),
        created_at=conversation["created_at"],
        last_message_at=last_message_at,
    )


def build_detail(conversation: dict, messages: list[dict]) -> ConversationDetail:
    """Build a read-only transcript response from DB rows."""
    return ConversationDetail(
        conversation=build_summary(conversation, messages),
        messages=[ConversationMessage.model_validate(row) for row in messages],
    )


async def list_app_history(
    db: AsyncClient,
    *,
    org_id: str,
    limit: int,
    before: datetime | None,
    agent_slug: str | None,
) -> ConversationPage:
    """Load one app history page with a single batched message query."""
    conversations, next_before = await list_channel_conversations(
        db,
        org_id=org_id,
        channel=APP_CHANNEL,
        channel_thread_id=agent_slug,
        limit=limit,
        before=before,
    )
    messages = await get_messages_for_conversations(
        db,
        [conversation["id"] for conversation in conversations],
    )
    grouped: dict[str, list[dict]] = {conversation["id"]: [] for conversation in conversations}
    for message in messages:
        grouped.setdefault(message["conversation_id"], []).append(message)

    return ConversationPage(
        conversations=[
            build_summary(conversation, grouped[conversation["id"]])
            for conversation in conversations
        ],
        next_before=next_before,
    )


async def get_app_history_detail(
    db: AsyncClient,
    *,
    org_id: str,
    conversation_id: str,
) -> ConversationDetail | None:
    """Load one org-scoped app transcript, returning None when unauthorized."""
    conversation = await get_channel_conversation(
        db,
        conversation_id=conversation_id,
        org_id=org_id,
        channel=APP_CHANNEL,
    )
    if conversation is None:
        return None
    messages = await get_conversation_messages(db, conversation_id)
    return build_detail(conversation, messages)


async def get_current_app_conversation(
    db: AsyncClient,
    *,
    org_id: str,
    agent_slug: str,
) -> ConversationDetail | None:
    """Hydrate the active app thread, excluding sessions expired by inactivity."""
    conversation = await get_active_conversation(
        db,
        org_id=org_id,
        channel=APP_CHANNEL,
        channel_thread_id=agent_slug,
    )
    if conversation is None:
        return None
    messages = await get_conversation_messages(db, conversation["id"])
    return build_detail(conversation, messages)
