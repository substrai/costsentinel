"""Budget enforcement for LLM API calls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from costsentinel.core.config import CostSentinelConfig, PolicyConfig
from costsentinel.core.state import CostState


@dataclass
class BudgetDecision:
    """Result of a budget check."""

    allowed: bool
    action: str  # "allow", "block", "downgrade", "alert"
    reason: str
    remaining: float
    limit: float


class BudgetExceededError(Exception):
    """Raised when a budget limit is exceeded and action is 'block'."""

    def __init__(
        self,
        message: str,
        scope: str = "",
        limit: float = 0.0,
        current: float = 0.0,
    ):
        super().__init__(message)
        self.scope = scope
        self.limit = limit
        self.current = current


class BudgetEnforcer:
    """Enforces budget policies by checking cost state against limits.

    Checks both daily and monthly limits and returns the most restrictive
    decision.
    """

    def __init__(self, config: CostSentinelConfig, state: CostState):
        """Initialize budget enforcer.

        Args:
            config: CostSentinel configuration with policies.
            state: Cost state store for reading current totals.
        """
        self._config = config
        self._state = state

    def check(
        self, scope: str, scope_id: str, estimated_cost: float = 0.0
    ) -> BudgetDecision:
        """Check if a call is within budget.

        Args:
            scope: One of "global", "team", "endpoint", "user".
            scope_id: Identifier within the scope.
            estimated_cost: Estimated cost of the upcoming call.

        Returns:
            BudgetDecision indicating whether the call is allowed.
        """
        policy = self._config.get_policy(scope)

        if policy is None:
            return BudgetDecision(
                allowed=True,
                action="allow",
                reason=f"No policy defined for scope '{scope}'",
                remaining=float("inf"),
                limit=0.0,
            )

        # Check max cost per request
        if policy.max_cost_per_request is not None:
            if estimated_cost > policy.max_cost_per_request:
                return BudgetDecision(
                    allowed=False,
                    action=policy.on_exceed,
                    reason=(
                        f"Estimated cost ${estimated_cost:.4f} exceeds "
                        f"max per-request limit ${policy.max_cost_per_request:.4f}"
                    ),
                    remaining=0.0,
                    limit=policy.max_cost_per_request,
                )

        # Check daily limit
        if policy.limit_daily is not None:
            daily_total = self._state.get_total(scope, scope_id, "daily")
            daily_remaining = policy.limit_daily - daily_total

            if daily_total + estimated_cost > policy.limit_daily:
                return BudgetDecision(
                    allowed=False,
                    action=policy.on_exceed,
                    reason=(
                        f"Daily budget exceeded for {scope}/{scope_id}: "
                        f"${daily_total:.4f} + ${estimated_cost:.4f} > "
                        f"${policy.limit_daily:.4f} limit"
                    ),
                    remaining=max(0.0, daily_remaining),
                    limit=policy.limit_daily,
                )

        # Check monthly limit
        if policy.limit_monthly is not None:
            monthly_total = self._state.get_total(scope, scope_id, "monthly")
            monthly_remaining = policy.limit_monthly - monthly_total

            if monthly_total + estimated_cost > policy.limit_monthly:
                return BudgetDecision(
                    allowed=False,
                    action=policy.on_exceed,
                    reason=(
                        f"Monthly budget exceeded for {scope}/{scope_id}: "
                        f"${monthly_total:.4f} + ${estimated_cost:.4f} > "
                        f"${policy.limit_monthly:.4f} limit"
                    ),
                    remaining=max(0.0, monthly_remaining),
                    limit=policy.limit_monthly,
                )

        # All checks passed
        remaining = self._calculate_remaining(policy, scope, scope_id)
        limit = policy.limit_daily or policy.limit_monthly or 0.0

        return BudgetDecision(
            allowed=True,
            action="allow",
            reason="Within budget",
            remaining=remaining,
            limit=limit,
        )

    def _calculate_remaining(
        self, policy: PolicyConfig, scope: str, scope_id: str
    ) -> float:
        """Calculate the most restrictive remaining budget."""
        remaining = float("inf")

        if policy.limit_daily is not None:
            daily_total = self._state.get_total(scope, scope_id, "daily")
            remaining = min(remaining, policy.limit_daily - daily_total)

        if policy.limit_monthly is not None:
            monthly_total = self._state.get_total(scope, scope_id, "monthly")
            remaining = min(remaining, policy.limit_monthly - monthly_total)

        return max(0.0, remaining) if remaining != float("inf") else 0.0
