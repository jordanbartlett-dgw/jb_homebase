from __future__ import annotations

import structlog
from posthog import Posthog

from jordan_claw.config import get_settings

log = structlog.get_logger()

_client: Posthog | None = None
_initialized: bool = False


def get_posthog() -> Posthog | None:
    """Lazy singleton. Returns None when PostHog is disabled or unkeyed."""
    global _client, _initialized
    if _initialized:
        return _client

    try:
        settings = get_settings()
    except Exception:
        # Settings unavailable (e.g. unit tests without env). Treat as disabled.
        _initialized = True
        _client = None
        return None

    _initialized = True

    if not settings.posthog_enabled or not settings.posthog_api_key:
        _client = None
        return None

    _client = Posthog(
        project_api_key=settings.posthog_api_key,
        host=settings.posthog_host,
    )
    log.info("posthog_client_initialized", host=settings.posthog_host)
    return _client


def shutdown_posthog() -> None:
    """Flush queued events. Safe to call when client was never initialized."""
    global _client, _initialized
    if _client is not None:
        try:
            _client.shutdown()
        except Exception:
            log.warning("posthog_shutdown_failed", exc_info=True)
    _client = None
    _initialized = False
