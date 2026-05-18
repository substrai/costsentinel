"""Tests for the pricing engine."""

import pytest

from costsentinel.core.pricing import PricingEngine, DEFAULT_PRICING, TOKENS_PER_WORD


class TestPricingEngine:
    """Test suite for PricingEngine."""

    def test_default_pricing_loaded(self):
        engine = PricingEngine()
        assert "claude-3.5-sonnet" in engine.models
        assert "claude-3-haiku" in engine.models
        assert "titan-embed" in engine.models

    def test_calculate_cost_claude_sonnet(self):
        engine = PricingEngine()
        # 1000 input tokens at $0.003/1K = $0.003
        # 500 output tokens at $0.015/1K = $0.0075
        cost = engine.calculate_cost("claude-3.5-sonnet", 1000, 500)
        assert cost == pytest.approx(0.0105, abs=1e-6)

    def test_calculate_cost_claude_haiku(self):
        engine = PricingEngine()
        # 1000 input tokens at $0.00025/1K = $0.00025
        # 500 output tokens at $0.00125/1K = $0.000625
        cost = engine.calculate_cost("claude-3-haiku", 1000, 500)
        assert cost == pytest.approx(0.000875, abs=1e-6)

    def test_calculate_cost_titan_embed(self):
        engine = PricingEngine()
        # 1000 input tokens at $0.0001/1K = $0.0001
        # Output is $0 for embeddings
        cost = engine.calculate_cost("titan-embed", 1000, 0)
        assert cost == pytest.approx(0.0001, abs=1e-6)

    def test_calculate_cost_zero_tokens(self):
        engine = PricingEngine()
        cost = engine.calculate_cost("claude-3-haiku", 0, 0)
        assert cost == 0.0

    def test_calculate_cost_large_token_count(self):
        engine = PricingEngine()
        # 100K input, 50K output for Claude 3.5 Sonnet
        # Input: 100 * $0.003 = $0.30
        # Output: 50 * $0.015 = $0.75
        cost = engine.calculate_cost("claude-3.5-sonnet", 100000, 50000)
        assert cost == pytest.approx(1.05, abs=1e-6)

    def test_unknown_model_raises(self):
        engine = PricingEngine()
        with pytest.raises(ValueError, match="Unknown model"):
            engine.calculate_cost("gpt-4-nonexistent", 100, 100)

    def test_get_model_price(self):
        engine = PricingEngine()
        price = engine.get_model_price("claude-3-haiku")
        assert price == {"input": 0.00025, "output": 0.00125}

    def test_custom_pricing_table(self):
        custom = {"my-model": {"input": 0.01, "output": 0.05}}
        engine = PricingEngine(custom)
        cost = engine.calculate_cost("my-model", 1000, 1000)
        assert cost == pytest.approx(0.06, abs=1e-6)
        # Default models should still be available
        assert "claude-3-haiku" in engine.models

    def test_estimate_cost(self):
        engine = PricingEngine()
        # "hello world" = 2 words * 1.3 = ~2.6 -> 2 tokens (int)
        # With max_output_tokens=100
        text = "hello world"
        cost = engine.estimate_cost("claude-3-haiku", text, max_output_tokens=100)
        # Input: int(2 * 1.3) = 2 tokens -> 2/1000 * 0.00025 = 0.0000005
        # Output: 100/1000 * 0.00125 = 0.000125
        assert cost > 0

    def test_estimate_cost_longer_text(self):
        engine = PricingEngine()
        text = " ".join(["word"] * 100)  # 100 words
        cost = engine.estimate_cost("claude-3.5-sonnet", text, max_output_tokens=500)
        # Input: int(100 * 1.3) = 130 tokens -> 130/1000 * 0.003 = 0.00039
        # Output: 500/1000 * 0.015 = 0.0075
        expected = 0.00039 + 0.0075
        assert cost == pytest.approx(expected, abs=1e-6)

    def test_add_model(self):
        engine = PricingEngine()
        engine.add_model("new-model", 0.005, 0.025)
        assert "new-model" in engine.models
        cost = engine.calculate_cost("new-model", 1000, 1000)
        assert cost == pytest.approx(0.03, abs=1e-6)

    def test_remove_model(self):
        engine = PricingEngine()
        engine.add_model("temp-model", 0.001, 0.002)
        engine.remove_model("temp-model")
        assert "temp-model" not in engine.models

    def test_remove_unknown_model_raises(self):
        engine = PricingEngine()
        with pytest.raises(ValueError):
            engine.remove_model("nonexistent")
