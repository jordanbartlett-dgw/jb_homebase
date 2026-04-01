from __future__ import annotations

from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    supabase_url: str
    supabase_service_key: str
    supabase_anon_key: str
    anthropic_api_key: str
    telegram_bot_token: str
    tavily_api_key: str
    default_org_id: str
    default_agent_slug: str = "claw-main"
    log_level: str = "INFO"
    environment: str = "development"
    message_history_limit: int = 50

    model_config = ConfigDict(env_file=".env")


def get_settings() -> Settings:
    return Settings()
