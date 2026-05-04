from __future__ import annotations

from decimal import Decimal

import structlog

log = structlog.get_logger()

# USD per 1M tokens. Source: anthropic.com/pricing as of 2026-04-15.
# Update this dict when Anthropic changes prices or you add a new model.
PRICING: dict[str, dict[str, Decimal]] = {
    "claude-sonnet-4-5-20250929": {"input": Decimal("3.00"), "output": Decimal("15.00")},
    "claude-haiku-4-5-20251001":  {"input": Decimal("1.00"), "output": Decimal("5.00")},
    "claude-sonnet-4-20250514":   {"input": Decimal("3.00"), "output": Decimal("15.00")},
}

_PER_MILLION = Decimal("1000000")


def compute_cost(model: str, input_tokens: int, output_tokens: int) -> Decimal | None:
    """Compute USD cost for a model run. Returns None for unknown models.

    Accepts both bare model IDs ('claude-sonnet-4-5-20250929') and
    Pydantic AI provider-prefixed IDs ('anthropic:claude-sonnet-4-5-20250929').
    """
    bare = model.split(":", 1)[1] if ":" in model else model
    pricing = PRICING.get(bare)
    if not pricing:
        log.warning("unknown_model_pricing", model=model)
        return None
    return (
        (Decimal(input_tokens) / _PER_MILLION) * pricing["input"]
        + (Decimal(output_tokens) / _PER_MILLION) * pricing["output"]
    )
