from __future__ import annotations

from unittest.mock import patch

from jordan_claw.analytics import posthog_client


def _reset_singleton() -> None:
    posthog_client._client = None
    posthog_client._initialized = False


def test_returns_none_when_no_api_key(monkeypatch):
    _reset_singleton()
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "k")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "k")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "k")
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    monkeypatch.setenv("FASTMAIL_USERNAME", "k")
    monkeypatch.setenv("FASTMAIL_APP_PASSWORD", "k")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("DEFAULT_ORG_ID", "org-1")
    monkeypatch.delenv("POSTHOG_API_KEY", raising=False)

    assert posthog_client.get_posthog() is None


def test_returns_none_when_disabled(monkeypatch):
    _reset_singleton()
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "k")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "k")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "k")
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    monkeypatch.setenv("FASTMAIL_USERNAME", "k")
    monkeypatch.setenv("FASTMAIL_APP_PASSWORD", "k")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("DEFAULT_ORG_ID", "org-1")
    monkeypatch.setenv("POSTHOG_API_KEY", "phc_test")
    monkeypatch.setenv("POSTHOG_ENABLED", "false")

    assert posthog_client.get_posthog() is None


def test_returns_singleton_when_configured(monkeypatch):
    _reset_singleton()
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "k")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "k")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "k")
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    monkeypatch.setenv("FASTMAIL_USERNAME", "k")
    monkeypatch.setenv("FASTMAIL_APP_PASSWORD", "k")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("DEFAULT_ORG_ID", "org-1")
    monkeypatch.setenv("POSTHOG_API_KEY", "phc_test")
    monkeypatch.setenv("POSTHOG_ENABLED", "true")

    with patch("jordan_claw.analytics.posthog_client.Posthog") as mock_cls:
        mock_cls.return_value = object()
        first = posthog_client.get_posthog()
        second = posthog_client.get_posthog()

    assert first is not None
    assert first is second
    mock_cls.assert_called_once()


def test_shutdown_calls_underlying_client(monkeypatch):
    _reset_singleton()
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "k")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "k")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "k")
    monkeypatch.setenv("TAVILY_API_KEY", "k")
    monkeypatch.setenv("FASTMAIL_USERNAME", "k")
    monkeypatch.setenv("FASTMAIL_APP_PASSWORD", "k")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("DEFAULT_ORG_ID", "org-1")
    monkeypatch.setenv("POSTHOG_API_KEY", "phc_test")

    with patch("jordan_claw.analytics.posthog_client.Posthog") as mock_cls:
        instance = mock_cls.return_value
        posthog_client.get_posthog()
        posthog_client.shutdown_posthog()

    instance.shutdown.assert_called_once()
    assert posthog_client._client is None
    assert posthog_client._initialized is False
