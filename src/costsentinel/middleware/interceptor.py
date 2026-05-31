"""Call interception middleware for LLM API cost tracking."""

from __future__ import annotations

import functools
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional, TypeVar, Union

from costsentinel.core.config import CostSentinelConfig, load_config
from costsentinel.core.pricing import PricingEngine
from costsentinel.core.state import CostState
from costsentinel.policies.attribution import AttributionStore, CostAttribution
from costsentinel.policies.budget import BudgetDecision, BudgetEnforcer, BudgetExceededError
from costsentinel.policies.rate_limit import RateLimiter, RateLimitDecision
from costsentinel.policies.circuit_breaker import CircuitBreaker, CircuitBreakerTripped, CircuitDecision


F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class CallResult:
    """Result of a tracked LLM API call."""

    response: Any = None
    cost: float = 0.0
    model_used: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    budget_remaining: float = 0.0
    decision: Optional[BudgetDecision] = None
    duration_ms: float = 0.0
    rate_limited: bool = False
    rate_limit_decision: Optional[RateLimitDecision] = None


class RateLimitExceededError(Exception):
    """Raised when a request exceeds the configured rate limit."""

    def __init__(self, scope: str, scope_id: str, decision: RateLimitDecision):
        self.scope = scope
        self.scope_id = scope_id
        self.decision = decision
        super().__init__(
            f"Rate limit exceeded for {scope}:{scope_id}. "
            f"Limit: {decision.limit}/min, remaining: {decision.remaining}. "
            f"Retry after: {decision.reset_at:.0f}"
        )


class CostMiddleware:
    """Middleware that intercepts LLM calls for cost tracking and budget enforcement.

    Usage:
        middleware = CostMiddleware("costsentinel.yaml")

        @middleware.intercept(model="claude-3-haiku", user_id="user-1", team_id="team-a")
        def call_llm(prompt):
            # your LLM call here
            return response, input_tokens, output_tokens

        # Or manual tracking:
        middleware.track_call("claude-3-haiku", input_tokens=500, output_tokens=200,
                            metadata={"user_id": "user-1", "team_id": "team-a"})
    """

    def __init__(self, config_or_path: Union[CostSentinelConfig, str, Path]):
        """Initialize middleware.

        Args:
            config_or_path: A CostSentinelConfig instance or path to YAML config file.
        """
        if isinstance(config_or_path, CostSentinelConfig):
            self._config = config_or_path
        else:
            self._config = load_config(str(config_or_path))

        self._pricing = PricingEngine(self._config.pricing)
        self._state = CostState(self._config.state_file)
        self._budget = BudgetEnforcer(self._config, self._state)
        self._attribution = AttributionStore(self._config.attribution_file)

        # Initialize rate limiter from config
        rate_limits = self._config.rate_limits or {}
        self._rate_limiter = RateLimiter(
            global_rpm=rate_limits.get("requests_per_minute", 1000),
            per_user_rpm=rate_limits.get("per_user_rpm", 30),
            per_team_rpm=rate_limits.get("per_team_rpm", 200),
        )

        # Initialize circuit breaker from config policies
        global_policy = self._config.get_policy("global")
        self._circuit_breaker = CircuitBreaker(
            max_cost_per_request=global_policy.max_cost_per_request if global_policy and global_policy.max_cost_per_request else 0.50,
            max_cost_per_session=5.00,
            max_tokens_per_request=8000,
        )

    @property
    def config(self) -> CostSentinelConfig:
        """Access the configuration."""
        return self._config

    @property
    def rate_limiter(self) -> RateLimiter:
        """Access the rate limiter."""
        return self._rate_limiter

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        """Access the circuit breaker."""
        return self._circuit_breaker

    def check_circuit_breaker(
        self,
        estimated_cost: float = 0.0,
        input_tokens: int = 0,
        session_id: Optional[str] = None,
    ) -> None:
        """Check circuit breaker limits before making an LLM call.

        Enforces per-request cost limits, per-request token limits,
        and per-session cumulative cost limits.

        Args:
            estimated_cost: Estimated cost of the upcoming request.
            input_tokens: Number of input tokens for the request.
            session_id: Optional session ID for session-level limits.

        Raises:
            CircuitBreakerTripped: If any circuit breaker threshold is exceeded.
        """
        # Check per-request limits
        request_decision = self._circuit_breaker.check_request(
            estimated_cost=estimated_cost, input_tokens=input_tokens
        )
        if not request_decision.allowed:
            raise CircuitBreakerTripped(
                request_decision.reason,
                threshold=request_decision.threshold,
                current=request_decision.current,
            )

        # Check per-session limits
        if session_id:
            session_decision = self._circuit_breaker.check_session(session_id)
            if not session_decision.allowed:
                raise CircuitBreakerTripped(
                    session_decision.reason,
                    threshold=session_decision.threshold,
                    current=session_decision.current,
                )

    def check_rate_limit(
        self,
        user_id: Optional[str] = None,
        team_id: Optional[str] = None,
    ) -> None:
        """Check rate limits before making an LLM call.

        Checks global, user, and team rate limits. Raises
        RateLimitExceededError if any limit is exceeded.

        Args:
            user_id: Optional user identifier for per-user limits.
            team_id: Optional team identifier for per-team limits.

        Raises:
            RateLimitExceededError: If any rate limit is exceeded.
        """
        # Check global rate limit
        global_decision = self._rate_limiter.check("global", "default")
        if not global_decision.allowed:
            raise RateLimitExceededError("global", "default", global_decision)

        # Check per-user rate limit
        if user_id:
            user_decision = self._rate_limiter.check("user", user_id)
            if not user_decision.allowed:
                raise RateLimitExceededError("user", user_id, user_decision)

        # Check per-team rate limit
        if team_id:
            team_decision = self._rate_limiter.check("team", team_id)
            if not team_decision.allowed:
                raise RateLimitExceededError("team", team_id, team_decision)

        # Consume tokens from all applicable buckets
        self._rate_limiter.consume("global", "default")
        if user_id:
            self._rate_limiter.consume("user", user_id)
        if team_id:
            self._rate_limiter.consume("team", team_id)

    @property
    def pricing(self) -> PricingEngine:
        """Access the pricing engine."""
        return self._pricing

    @property
    def state(self) -> CostState:
        """Access the state store."""
        return self._state

    @property
    def budget(self) -> BudgetEnforcer:
        """Access the budget enforcer."""
        return self._budget

    def intercept(
        self,
        model: str = "claude-3-haiku",
        user_id: Optional[str] = None,
        team_id: Optional[str] = None,
        endpoint: Optional[str] = None,
    ) -> Callable[[F], F]:
        """Decorator that wraps a function making LLM calls.

        The decorated function must return a tuple of:
            (response, input_tokens, output_tokens)

        Args:
            model: Model identifier for pricing.
            user_id: User making the call.
            team_id: Team the user belongs to.
            endpoint: API endpoint being called.

        Returns:
            Decorator function.
        """

        def decorator(func: F) -> F:
            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> CallResult:
                # Estimate cost for pre-check
                estimated_cost = self._pricing.calculate_cost(model, 1000, 500)

                # Check budget before call
                decision = self._pre_check(
                    model, estimated_cost, user_id, team_id, endpoint
                )

                if not decision.allowed:
                    if decision.action == "block":
                        raise BudgetExceededError(
                            f"Budget exceeded: {decision.reason}",
                            scope=decision.action,
                            limit=decision.limit,
                            current=decision.limit - decision.remaining,
                        )

                # Execute the function
                start = time.time()
                result = func(*args, **kwargs)
                duration_ms = (time.time() - start) * 1000

                # Parse result - expect (response, input_tokens, output_tokens)
                if isinstance(result, tuple) and len(result) == 3:
                    response, tokens_in, tokens_out = result
                else:
                    response = result
                    tokens_in, tokens_out = 0, 0

                # Calculate actual cost
                cost = self._pricing.calculate_cost(model, tokens_in, tokens_out)

                # Record the cost
                self._record_cost(cost, model, tokens_in, tokens_out, user_id, team_id, endpoint)

                # Get remaining budget
                remaining = self._get_remaining(user_id, team_id, endpoint)

                return CallResult(
                    response=response,
                    cost=cost,
                    model_used=model,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    budget_remaining=remaining,
                    decision=decision,
                    duration_ms=duration_ms,
                )

            return wrapper  # type: ignore

        return decorator

    def track_call(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CallResult:
        """Manually track an LLM API call.

        Args:
            model: Model identifier.
            input_tokens: Number of input tokens used.
            output_tokens: Number of output tokens used.
            metadata: Optional dict with user_id, team_id, endpoint.

        Returns:
            CallResult with cost information.
        """
        metadata = metadata or {}
        user_id = metadata.get("user_id")
        team_id = metadata.get("team_id")
        endpoint = metadata.get("endpoint")

        cost = self._pricing.calculate_cost(model, input_tokens, output_tokens)

        # Check budget
        decision = self._pre_check(model, cost, user_id, team_id, endpoint)

        if not decision.allowed and decision.action == "block":
            raise BudgetExceededError(
                f"Budget exceeded: {decision.reason}",
                scope="budget",
                limit=decision.limit,
                current=decision.limit - decision.remaining,
            )

        # Record the cost
        self._record_cost(cost, model, input_tokens, output_tokens, user_id, team_id, endpoint)

        remaining = self._get_remaining(user_id, team_id, endpoint)

        return CallResult(
            response=None,
            cost=cost,
            model_used=model,
            tokens_in=input_tokens,
            tokens_out=output_tokens,
            budget_remaining=remaining,
            decision=decision,
        )

    def _pre_check(
        self,
        model: str,
        estimated_cost: float,
        user_id: Optional[str],
        team_id: Optional[str],
        endpoint: Optional[str],
    ) -> BudgetDecision:
        """Run budget pre-checks for all applicable scopes."""
        # Check from most specific to least specific
        scopes_to_check = [
            ("user", user_id),
            ("endpoint", endpoint),
            ("team", team_id),
            ("global", "default"),
        ]

        for scope, scope_id in scopes_to_check:
            if scope_id is None:
                continue
            decision = self._budget.check(scope, scope_id, estimated_cost)
            if not decision.allowed:
                return decision

        return BudgetDecision(
            allowed=True,
            action="allow",
            reason="Within budget",
            remaining=0.0,
            limit=0.0,
        )

    def _record_cost(
        self,
        cost: float,
        model: str,
        tokens_in: int,
        tokens_out: int,
        user_id: Optional[str],
        team_id: Optional[str],
        endpoint: Optional[str],
    ) -> None:
        """Record cost to state store and attribution."""
        # Update state for all applicable scopes
        self._state.increment("global", "default", cost)
        if team_id:
            self._state.increment("team", team_id, cost)
        if endpoint:
            self._state.increment("endpoint", endpoint, cost)
        if user_id:
            self._state.increment("user", user_id, cost)

        # Record attribution
        attribution = CostAttribution(
            user_id=user_id or "unknown",
            team_id=team_id or "unknown",
            endpoint=endpoint or "unknown",
            model=model,
            timestamp=datetime.now(timezone.utc).isoformat(),
            cost=cost,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
        self._attribution.record(attribution)

    def _get_remaining(
        self,
        user_id: Optional[str],
        team_id: Optional[str],
        endpoint: Optional[str],
    ) -> float:
        """Get the most restrictive remaining budget."""
        remaining = float("inf")

        scopes_to_check = [
            ("user", user_id),
            ("endpoint", endpoint),
            ("team", team_id),
            ("global", "default"),
        ]

        for scope, scope_id in scopes_to_check:
            if scope_id is None:
                continue
            policy = self._config.get_policy(scope)
            if policy and policy.limit_daily:
                current = self._state.get_total(scope, scope_id, "daily")
                scope_remaining = policy.limit_daily - current
                remaining = min(remaining, scope_remaining)

        return remaining if remaining != float("inf") else 0.0


# Module-level singleton for simple usage
_default_middleware: Optional[CostMiddleware] = None


def _get_default_middleware() -> CostMiddleware:
    """Get or create the default middleware instance."""
    global _default_middleware
    if _default_middleware is None:
        _default_middleware = CostMiddleware(load_config())
    return _default_middleware


def cost_tracked(
    model: str = "claude-3-haiku",
    user_id: Optional[str] = None,
    team_id: Optional[str] = None,
    endpoint: Optional[str] = None,
) -> Callable[[F], F]:
    """Convenience decorator for cost tracking using default config.

    Usage:
        @cost_tracked(model="claude-3-haiku", user_id="user-1")
        def my_llm_call(prompt):
            return response, input_tokens, output_tokens
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> CallResult:
            middleware = _get_default_middleware()
            tracked_func = middleware.intercept(
                model=model, user_id=user_id, team_id=team_id, endpoint=endpoint
            )(func)
            return tracked_func(*args, **kwargs)

        return wrapper  # type: ignore

    return decorator
