"""Cost optimization suggestions based on usage patterns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class OptimizationSuggestion:
    """A cost optimization recommendation."""

    category: str  # model_routing | token_reduction | caching | scheduling
    title: str
    description: str
    estimated_savings_pct: float
    priority: str  # high | medium | low
    action: str


class CostOptimizer:
    """Analyzes usage patterns and suggests cost optimizations.

    Identifies opportunities for model downgrading, token reduction,
    caching, and scheduling optimizations.
    """

    def analyze(
        self,
        usage_data: List[Dict[str, Any]],
        current_model: str = "claude-3-sonnet",
    ) -> List[OptimizationSuggestion]:
        """Analyze usage data and generate optimization suggestions.

        Args:
            usage_data: List of usage records with model, tokens, cost, complexity.
            current_model: The currently configured default model.

        Returns:
            List of optimization suggestions sorted by estimated savings.
        """
        suggestions: List[OptimizationSuggestion] = []

        if not usage_data:
            return suggestions

        # Check for model downgrade opportunities
        suggestion = self._check_model_downgrade(usage_data, current_model)
        if suggestion:
            suggestions.append(suggestion)

        # Check for token waste
        suggestion = self._check_token_waste(usage_data)
        if suggestion:
            suggestions.append(suggestion)

        # Check for caching opportunities
        suggestion = self._check_caching(usage_data)
        if suggestion:
            suggestions.append(suggestion)

        # Check for off-peak scheduling
        suggestion = self._check_scheduling(usage_data)
        if suggestion:
            suggestions.append(suggestion)

        # Sort by estimated savings
        suggestions.sort(key=lambda s: s.estimated_savings_pct, reverse=True)
        return suggestions

    def _check_model_downgrade(
        self, usage_data: List[Dict[str, Any]], current_model: str
    ) -> Optional[OptimizationSuggestion]:
        """Check if simpler queries could use a cheaper model."""
        simple_queries = [
            d for d in usage_data
            if d.get("complexity", 0.5) < 0.3
        ]

        if len(simple_queries) > len(usage_data) * 0.3:
            pct = len(simple_queries) / len(usage_data) * 100
            return OptimizationSuggestion(
                category="model_routing",
                title="Enable model routing for simple queries",
                description=f"{pct:.0f}% of queries are simple and could use a cheaper model (e.g., Haiku instead of Sonnet)",
                estimated_savings_pct=pct * 0.6,  # ~60% cost reduction on those queries
                priority="high",
                action="Enable cost.optimization.model_routing in config",
            )
        return None

    def _check_token_waste(self, usage_data: List[Dict[str, Any]]) -> Optional[OptimizationSuggestion]:
        """Check for high output/input token ratios indicating waste."""
        high_ratio = [
            d for d in usage_data
            if d.get("output_tokens", 0) > d.get("input_tokens", 1) * 3
        ]

        if len(high_ratio) > len(usage_data) * 0.2:
            return OptimizationSuggestion(
                category="token_reduction",
                title="Reduce output token waste",
                description="20%+ of requests have output tokens 3x+ input. Consider adding max_tokens limits or more specific prompts.",
                estimated_savings_pct=15.0,
                priority="medium",
                action="Add max_tokens constraints to prompts or enable output truncation",
            )
        return None

    def _check_caching(self, usage_data: List[Dict[str, Any]]) -> Optional[OptimizationSuggestion]:
        """Check for repeated identical queries that could be cached."""
        queries = [d.get("query", "") for d in usage_data if d.get("query")]
        if not queries:
            return None

        unique_queries = set(queries)
        duplicate_ratio = 1.0 - (len(unique_queries) / len(queries))

        if duplicate_ratio > 0.2:
            return OptimizationSuggestion(
                category="caching",
                title="Enable response caching",
                description=f"{duplicate_ratio*100:.0f}% of queries are duplicates. Caching could eliminate redundant LLM calls.",
                estimated_savings_pct=duplicate_ratio * 80,
                priority="high",
                action="Enable query caching with TTL in config",
            )
        return None

    def _check_scheduling(self, usage_data: List[Dict[str, Any]]) -> Optional[OptimizationSuggestion]:
        """Check if batch processing could reduce costs."""
        total = len(usage_data)
        if total < 50:
            return None

        # Check if many requests happen in bursts
        timestamps = sorted(d.get("timestamp", 0) for d in usage_data if d.get("timestamp"))
        if len(timestamps) < 10:
            return None

        # Check for burst patterns (many requests within short windows)
        bursts = 0
        for i in range(1, len(timestamps)):
            if timestamps[i] - timestamps[i - 1] < 1.0:  # Within 1 second
                bursts += 1

        if bursts > total * 0.3:
            return OptimizationSuggestion(
                category="scheduling",
                title="Consider batch processing",
                description="30%+ of requests arrive in bursts. Batching could reduce per-request overhead and enable bulk pricing.",
                estimated_savings_pct=10.0,
                priority="low",
                action="Implement request batching for non-real-time workloads",
            )
        return None
