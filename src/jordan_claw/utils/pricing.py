from __future__ import annotations

from decimal import Decimal

import structlog

log = structlog.get_logger()

# USD per 1M tokens. Source: platform.claude.com/docs/en/about-claude/pricing as of 2026-07-26.
# Update this dict when Anthropic changes prices or you add a new model.
PRICING: dict[str, dict[str, Decimal]] = {
    "claude-sonnet-4-5-20250929": {"input": Decimal("3.00"), "output": Decimal("15.00")},
    "claude-haiku-4-5-20251001": {"input": Decimal("1.00"), "output": Decimal("5.00")},
    # Retired 2026-06-15; kept so historical usage_events rows still price
    "claude-sonnet-4-20250514": {"input": Decimal("3.00"), "output": Decimal("15.00")},
    # Sticker rates; intro pricing ($2/$10) runs through 2026-08-31, so this
    # overcounts slightly until then
    "claude-sonnet-5": {"input": Decimal("3.00"), "output": Decimal("15.00")},
}

_PER_MILLION = Decimal("1000000")

# Anthropic prompt caching multipliers, applied to the base input rate.
# Source: platform.claude.com/docs/en/build-with-claude/prompt-caching as of
# 2026-07-26 — cache writes cost 1.25x base input, cache reads cost 0.10x base
# input. `RunUsage.input_tokens` is cache-INCLUSIVE (pydantic-ai folds
# cache_read_tokens/cache_write_tokens into it), so uncached input must be
# derived by subtracting both out before applying the base rate.
CACHE_WRITE_MULTIPLIER = Decimal("1.25")
CACHE_READ_MULTIPLIER = Decimal("0.10")

# USD per audio minute. Source: openai.com/api/pricing (whisper-1), verified
# 2026-07-26. whisper-1 is deprecated and no longer listed on OpenAI's current
# pricing page, so this rate was cross-checked against third-party pricing
# aggregators instead.
WHISPER_PRICE_PER_MINUTE = Decimal("0.006")

# USD per 1M tokens, standard tier. Source: openai.com/api/pricing
# (text-embedding-3-small), verified 2026-07-26.
EMBEDDING_PRICING: dict[str, Decimal] = {
    "text-embedding-3-small": Decimal("0.02"),
}


def compute_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    *,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> Decimal | None:
    """Compute USD cost for a model run. Returns None for unknown models.

    Accepts both bare model IDs ('claude-sonnet-4-5-20250929') and
    Pydantic AI provider-prefixed IDs ('anthropic:claude-sonnet-4-5-20250929').

    `input_tokens` is cache-inclusive (see module note above), so the
    uncached portion billed at the base rate is
    `max(input_tokens - cache_read_tokens - cache_write_tokens, 0)`.
    """
    bare = model.split(":", 1)[1] if ":" in model else model
    pricing = PRICING.get(bare)
    if not pricing:
        log.warning("unknown_model_pricing", model=model)
        return None
    in_rate = pricing["input"]
    uncached_input = max(input_tokens - cache_read_tokens - cache_write_tokens, 0)
    return (
        (Decimal(uncached_input) / _PER_MILLION) * in_rate
        + (Decimal(cache_write_tokens) / _PER_MILLION) * in_rate * CACHE_WRITE_MULTIPLIER
        + (Decimal(cache_read_tokens) / _PER_MILLION) * in_rate * CACHE_READ_MULTIPLIER
        + (Decimal(output_tokens) / _PER_MILLION) * pricing["output"]
    )


def compute_transcription_cost(duration_seconds: float) -> Decimal:
    """Compute USD cost for a Whisper transcription call."""
    minutes = Decimal(str(duration_seconds)) / Decimal("60")
    return minutes * WHISPER_PRICE_PER_MINUTE


def compute_embedding_cost(model: str, tokens: int) -> Decimal | None:
    """Compute USD cost for an embedding call. Returns None for unknown models."""
    rate = EMBEDDING_PRICING.get(model)
    if rate is None:
        log.warning("unknown_embedding_pricing", model=model)
        return None
    return (Decimal(tokens) / _PER_MILLION) * rate
