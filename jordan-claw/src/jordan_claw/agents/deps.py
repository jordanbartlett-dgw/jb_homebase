from __future__ import annotations

from pydantic import BaseModel


class AgentDeps(BaseModel):
    """Credentials and context passed to tools via RunContext[AgentDeps]."""

    org_id: str
    tavily_api_key: str
    fastmail_username: str
    fastmail_app_password: str
