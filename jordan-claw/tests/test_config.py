from __future__ import annotations

import os

from jordan_claw.config import Settings


def test_settings_includes_fastmail_fields():
    """Settings should accept Fastmail credentials."""
    env = {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-key",
        "SUPABASE_ANON_KEY": "test-anon",
        "ANTHROPIC_API_KEY": "test-anthropic",
        "TELEGRAM_BOT_TOKEN": "test-bot",
        "TAVILY_API_KEY": "test-tavily",
        "DEFAULT_ORG_ID": "test-org",
        "FASTMAIL_USERNAME": "jordan@fastmail.com",
        "FASTMAIL_APP_PASSWORD": "app-password-123",
    }
    for k, v in env.items():
        os.environ[k] = v

    try:
        settings = Settings()
        assert settings.fastmail_username == "jordan@fastmail.com"
        assert settings.fastmail_app_password == "app-password-123"
    finally:
        for k in env:
            os.environ.pop(k, None)
