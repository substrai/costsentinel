"""Gradual model degradation based on budget consumption."""

from __future__ import annotations

from typing import Dict, List, Optional


class GradualDegrader:
    """Implements progressive model downgrade as budget depletes.

    Levels:
        0 = Premium (budget > 50% remaining)
        1 = Standard (20-50% remaining)
        2 = Economy (< 20% remaining)
        3 = Blocked (0% remaining)
    """

    def __init__(
        self,
        models: Optional[Dict[int, str]] = None,
        boundaries: Optional[List[float]] = None,
    ):
        """Initialize gradual degrader.

        Args:
            models: Dict mapping degradation level (0-3) to model name.
            boundaries: List of budget-remaining percentages for tier boundaries.
                Default: [0.50, 0.20, 0.0] meaning:
                  > 50% remaining = level 0 (premium)
                  20-50% remaining = level 1 (standard)
                  0-20% remaining = level 2 (economy)
                  0% remaining = level 3 (blocked)
        """
        self.models = models or {
            0: "claude-3.5-sonnet",
            1: "claude-3-sonnet",
            2: "claude-3-haiku",
            3: "",  # blocked
        }
        self.boundaries = boundaries or [0.50, 0.20, 0.0]

    def get_degradation_level(self, budget_pct_remaining: float) -> int:
        """Get degradation level based on remaining budget percentage.

        Args:
            budget_pct_remaining: Percentage of budget remaining (0.0-1.0).

        Returns:
            Degradation level 0-3.
        """
        if budget_pct_remaining <= 0:
            return 3
        if budget_pct_remaining <= self.boundaries[1]:
            return 2
        if budget_pct_remaining <= self.boundaries[0]:
            return 1
        return 0

    def get_model(self, budget_pct_remaining: float) -> str:
        """Get the appropriate model for the current budget state.

        Args:
            budget_pct_remaining: Percentage of budget remaining (0.0-1.0).

        Returns:
            Model name for the current degradation level.
        """
        level = self.get_degradation_level(budget_pct_remaining)
        return self.models.get(level, "")

    def is_blocked(self, budget_pct_remaining: float) -> bool:
        """Check if requests should be blocked.

        Args:
            budget_pct_remaining: Percentage of budget remaining (0.0-1.0).

        Returns:
            True if budget is exhausted and requests should be blocked.
        """
        return self.get_degradation_level(budget_pct_remaining) >= 3
