from __future__ import annotations

from pydantic import BaseModel


class IncomingMessage(BaseModel):
    """Channel-agnostic inbound message. Every adapter produces this."""

    channel: str
    channel_thread_id: str
    channel_message_id: str
    content: str
    org_id: str


class GatewayResponse(BaseModel):
    """Channel-agnostic response. Gateway returns this to every adapter."""

    content: str
    conversation_id: str
    token_count: int | None = None
    model: str | None = None
