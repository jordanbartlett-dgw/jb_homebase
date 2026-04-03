from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class AgentDeps(BaseModel):
    """Credentials and context passed to tools via RunContext[AgentDeps]."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    org_id: str
    tavily_api_key: str
    fastmail_username: str
    fastmail_app_password: str
    supabase_client: Any = None
