from __future__ import annotations

from decimal import Decimal

import pytest

from jordan_claw.utils.pricing import (
    EMBEDDING_PRICING,
    PRICING,
    WHISPER_PRICE_PER_MINUTE,
    compute_cost,
    compute_embedding_cost,
    compute_transcription_cost,
)


def test_compute_cost_known_sonnet_model():
    cost = compute_cost("claude-sonnet-4-5-20250929", 1_000_000, 0)
    assert cost == Decimal("3.00")


def test_compute_cost_known_haiku_model():
    cost = compute_cost("claude-haiku-4-5-20251001", 0, 1_000_000)
    assert cost == Decimal("5.00")


def test_compute_cost_combines_input_and_output():
    cost = compute_cost("claude-sonnet-4-5-20250929", 500_000, 100_000)
    assert cost == Decimal("3.00") * Decimal("0.5") + Decimal("15.00") * Decimal("0.1")


def test_compute_cost_zero_tokens_is_zero():
    assert compute_cost("claude-sonnet-4-5-20250929", 0, 0) == Decimal("0")


def test_compute_cost_unknown_model_returns_none(caplog: pytest.LogCaptureFixture):
    cost = compute_cost("anthropic:claude-future-model", 100, 50)
    assert cost is None


def test_compute_cost_strips_provider_prefix():
    """Pydantic AI model strings like 'anthropic:claude-...' should resolve."""
    bare = compute_cost("claude-sonnet-4-5-20250929", 1000, 1000)
    prefixed = compute_cost("anthropic:claude-sonnet-4-5-20250929", 1000, 1000)
    assert bare == prefixed


def test_pricing_table_has_known_models():
    """Sanity: catch accidental deletion of the pricing dict."""
    assert "claude-sonnet-4-5-20250929" in PRICING
    assert "claude-haiku-4-5-20251001" in PRICING
    for model, prices in PRICING.items():
        assert "input" in prices, f"{model} missing input price"
        assert "output" in prices, f"{model} missing output price"
        assert prices["input"] > 0
        assert prices["output"] > 0


def test_compute_cost_zero_cache_matches_old_values():
    """Backward compat: no cache kwargs must reproduce pre-cache-aware costs exactly."""
    cost = compute_cost("claude-sonnet-4-5-20250929", 500_000, 100_000)
    assert cost == Decimal("3.00") * Decimal("0.5") + Decimal("15.00") * Decimal("0.1")


def test_compute_cost_pure_cache_read_discount():
    """A run that is 100% cache reads (RunUsage.input_tokens is cache-inclusive)
    should bill at 10% of the base input rate, not the full input rate."""
    # sonnet-4-5: input $3.00/1M. 1M cache-read tokens, 0 uncached, 0 output.
    cost = compute_cost(
        "claude-sonnet-4-5-20250929",
        1_000_000,
        0,
        cache_read_tokens=1_000_000,
        cache_write_tokens=0,
    )
    assert cost == Decimal("3.00") * Decimal("0.10")


def test_compute_cost_cache_write_premium():
    """A run that is 100% cache writes should bill at 125% of the base input rate."""
    cost = compute_cost(
        "claude-sonnet-4-5-20250929",
        1_000_000,
        0,
        cache_read_tokens=0,
        cache_write_tokens=1_000_000,
    )
    assert cost == Decimal("3.00") * Decimal("1.25")


def test_compute_cost_mixed_cache_and_uncached():
    """input_tokens is cache-inclusive: uncached = input - cache_read - cache_write."""
    # 1M input total: 200k cache_read, 100k cache_write, 700k uncached; 50k output.
    cost = compute_cost(
        "claude-sonnet-4-5-20250929",
        1_000_000,
        50_000,
        cache_read_tokens=200_000,
        cache_write_tokens=100_000,
    )
    in_rate = Decimal("3.00")
    out_rate = Decimal("15.00")
    per_million = Decimal("1000000")
    expected = (
        (Decimal(700_000) / per_million) * in_rate
        + (Decimal(100_000) / per_million) * in_rate * Decimal("1.25")
        + (Decimal(200_000) / per_million) * in_rate * Decimal("0.10")
        + (Decimal(50_000) / per_million) * out_rate
    )
    assert cost == expected


def test_compute_cost_cache_tokens_exceeding_input_clamped_to_zero_uncached():
    """Defensive: if cache_read + cache_write somehow exceeds input_tokens
    (e.g. inconsistent provider data), uncached must clamp to 0, not go negative."""
    cost = compute_cost(
        "claude-sonnet-4-5-20250929",
        100,
        0,
        cache_read_tokens=80,
        cache_write_tokens=80,
    )
    in_rate = Decimal("3.00")
    per_million = Decimal("1000000")
    expected = (Decimal(80) / per_million) * in_rate * Decimal("1.25") + (
        Decimal(80) / per_million
    ) * in_rate * Decimal("0.10")
    assert cost == expected


def test_compute_transcription_cost_known_duration():
    # 90 seconds = 1.5 minutes @ $0.006/min
    cost = compute_transcription_cost(90.0)
    assert cost == Decimal("0.009")


def test_compute_transcription_cost_zero_duration():
    assert compute_transcription_cost(0.0) == Decimal("0")


def test_whisper_price_per_minute_constant():
    assert Decimal("0.006") == WHISPER_PRICE_PER_MINUTE


def test_compute_embedding_cost_known_model():
    # text-embedding-3-small: $0.02 / 1M tokens
    cost = compute_embedding_cost("text-embedding-3-small", 500_000)
    assert cost == Decimal("0.01")


def test_compute_embedding_cost_unknown_model_returns_none():
    assert compute_embedding_cost("text-embedding-unknown", 1_000) is None


def test_embedding_pricing_table_has_known_model():
    assert "text-embedding-3-small" in EMBEDDING_PRICING
    assert EMBEDDING_PRICING["text-embedding-3-small"] == Decimal("0.02")
