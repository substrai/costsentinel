"""Token pricing engine for LLM API calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

# Default pricing per 1K tokens
DEFAULT_PRICING: Dict[str, Dict[str, float]] = {
    "claude-3.5-sonnet": {"input": 0.003, "output": 0.015},
    "claude-3-sonnet": {"input": 0.003, "output": 0.015},
    "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
    "titan-embed": {"input": 0.0001, "output": 0.0},
}

# Heuristic: average tokens per word
TOKENS_PER_WORD: float = 1.3


class PricingEngine:
    """Calculates costs for LLM API calls based on token usage.

    Pricing is configured per model with separate input/output rates
    expressed as cost per 1,000 tokens.
    """

    def __init__(self, pricing_table: Optional[Dict[str, Dict[str, float]]] = None):
        """Initialize with a pricing table.

        Args:
            pricing_table: Dict mapping model names to {"input": rate, "output": rate}
                          where rates are cost per 1K tokens. Uses defaults if None.
        """
        self._pricing = dict(DEFAULT_PRICING)
        if pricing_table:
            self._pricing.update(pricing_table)

    @property
    def models(self) -> list:
        """List all known model names."""
        return list(self._pricing.keys())

    def calculate_cost(
        self, model: str, input_tokens: int, output_tokens: int
    ) -> float:
        """Calculate the cost of an API call.

        Args:
            model: Model identifier (e.g., "claude-3.5-sonnet").
            input_tokens: Number of input/prompt tokens.
            output_tokens: Number of output/completion tokens.

        Returns:
            Total cost in USD.

        Raises:
            ValueError: If the model is not in the pricing table.
        """
        prices = self.get_model_price(model)
        input_cost = (input_tokens / 1000.0) * prices["input"]
        output_cost = (output_tokens / 1000.0) * prices["output"]
        return round(input_cost + output_cost, 8)

    def get_model_price(self, model: str) -> Dict[str, float]:
        """Get pricing for a specific model.

        Args:
            model: Model identifier.

        Returns:
            Dict with "input" and "output" rates per 1K tokens.

        Raises:
            ValueError: If the model is not in the pricing table.
        """
        if model not in self._pricing:
            raise ValueError(
                f"Unknown model '{model}'. Known models: {list(self._pricing.keys())}"
            )
        return self._pricing[model]

    def estimate_cost(
        self, model: str, input_text: str, max_output_tokens: int = 1000
    ) -> float:
        """Estimate cost before making an API call.

        Uses a heuristic of ~1.3 tokens per word to estimate input tokens.

        Args:
            model: Model identifier.
            input_text: The input/prompt text.
            max_output_tokens: Maximum expected output tokens.

        Returns:
            Estimated cost in USD (upper bound based on max_output_tokens).
        """
        word_count = len(input_text.split())
        estimated_input_tokens = int(word_count * TOKENS_PER_WORD)
        return self.calculate_cost(model, estimated_input_tokens, max_output_tokens)

    def add_model(self, model: str, input_rate: float, output_rate: float) -> None:
        """Add or update a model's pricing.

        Args:
            model: Model identifier.
            input_rate: Cost per 1K input tokens.
            output_rate: Cost per 1K output tokens.
        """
        self._pricing[model] = {"input": input_rate, "output": output_rate}

    def remove_model(self, model: str) -> None:
        """Remove a model from the pricing table.

        Args:
            model: Model identifier.

        Raises:
            ValueError: If the model is not in the pricing table.
        """
        if model not in self._pricing:
            raise ValueError(f"Unknown model '{model}'.")
        del self._pricing[model]
