from __future__ import annotations

from pydantic_ai import RunUsage


def extract_usage(usage: RunUsage) -> dict:
    """Extract token counts from a Pydantic AI RunUsage object."""
    return {
        "input_tokens": usage.input_tokens or 0,
        "output_tokens": usage.output_tokens or 0,
        "total_tokens": (usage.input_tokens or 0) + (usage.output_tokens or 0),
        "requests": usage.requests or 0,
    }
