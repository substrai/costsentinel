"""Model routing engine - selects model based on budget state and query complexity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class RoutingDecision:
    """Result of a model routing decision."""

    model: str
    tier: str
    reason: str
    original_model: Optional[str] = None


class ModelRouter:
    """Routes LLM calls to appropriate model tiers based on budget state.

    Selects cheaper models as budget depletes, enabling graceful degradation
    instead of hard blocks.
    """

    def __init__(
        self,
        models: Optional[Dict[str, str]] = None,
        downgrade_at: float = 0.80,
        block_at: float = 1.00,
    ):
        """Initialize model router.

        Args:
            models: Dict mapping tier names to model identifiers.
                Default: tier_1=claude-3.5-sonnet, tier_2=claude-3-sonnet, tier_3=claude-3-haiku
            downgrade_at: Budget consumption percentage to start downgrading (0.0-1.0).
            block_at: Budget consumption percentage to block requests (0.0-1.0).
        """
        self.models = models or {
            "tier_1": "claude-3.5-sonnet",
            "tier_2": "claude-3-sonnet",
            "tier_3": "claude-3-haiku",
        }
        self.downgrade_at = downgrade_at
        self.block_at = block_at

    def get_current_tier(self, budget_consumed_pct: float) -> str:
        """Determine the current tier based on budget consumption.

        Args:
            budget_consumed_pct: Percentage of budget consumed (0.0-1.0).

        Returns:
            Tier name: "tier_1", "tier_2", "tier_3", or "blocked".
        """
        if budget_consumed_pct >= self.block_at:
            return "blocked"
        if budget_consumed_pct >= self.downgrade_at:
            # Between downgrade_at and block_at: use economy tier
            return "tier_3"
        if budget_consumed_pct >= self.downgrade_at * 0.6:
            # Between 60% of downgrade threshold and downgrade: use standard
            return "tier_2"
        return "tier_1"

    def route(
        self,
        budget_consumed_pct: float,
        original_model: Optional[str] = None,
    ) -> RoutingDecision:
        """Route to appropriate model based on budget state.

        Args:
            budget_consumed_pct: Percentage of budget consumed (0.0-1.0).
            original_model: The model originally requested.

        Returns:
            RoutingDecision with selected model and reasoning.
        """
        tier = self.get_current_tier(budget_consumed_pct)

        if tier == "blocked":
            return RoutingDecision(
                model="",
                tier="blocked",
                reason=f"Budget exhausted ({budget_consumed_pct:.0%} consumed, block at {self.block_at:.0%})",
                original_model=original_model,
            )

        model = self.models.get(tier, self.models.get("tier_3", "claude-3-haiku"))

        if original_model and model == original_model:
            reason = f"Using requested model (budget at {budget_consumed_pct:.0%})"
        elif original_model:
            reason = f"Downgraded from {original_model} (budget at {budget_consumed_pct:.0%})"
        else:
            reason = f"Selected {tier} model (budget at {budget_consumed_pct:.0%})"

        return RoutingDecision(
            model=model,
            tier=tier,
            reason=reason,
            original_model=original_model,
        )
