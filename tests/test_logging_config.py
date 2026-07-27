from __future__ import annotations

import structlog

from jordan_claw.main import configure_logging


def test_configure_logging_bridges_logfire_when_enabled():
    """logfire_enabled=True inserts logfire.StructlogProcessor into the chain."""
    try:
        configure_logging("development", "INFO", logfire_enabled=True)
        processors = structlog.get_config()["processors"]
        processor_classes = [type(p).__name__ for p in processors]
        assert "LogfireProcessor" in processor_classes
    finally:
        structlog.reset_defaults()


def test_configure_logging_omits_logfire_by_default():
    """logfire_enabled defaults to False: no logfire processor in the chain."""
    try:
        configure_logging("development", "INFO")
        processors = structlog.get_config()["processors"]
        processor_classes = [type(p).__name__ for p in processors]
        assert "LogfireProcessor" not in processor_classes
    finally:
        structlog.reset_defaults()
