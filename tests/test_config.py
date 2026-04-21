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
        "OPENAI_API_KEY": "test-openai",
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


def test_settings_has_openai_api_key(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "test-anon")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-bot")
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily")
    monkeypatch.setenv("FASTMAIL_USERNAME", "test@fastmail.com")
    monkeypatch.setenv("FASTMAIL_APP_PASSWORD", "test-pw")
    monkeypatch.setenv("DEFAULT_ORG_ID", "org-123")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    settings = Settings()
    assert settings.openai_api_key == "test-openai"
