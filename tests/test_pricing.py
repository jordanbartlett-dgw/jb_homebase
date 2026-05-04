from __future__ import annotations

from decimal import Decimal

import pytest

from jordan_claw.utils.pricing import PRICING, compute_cost


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
