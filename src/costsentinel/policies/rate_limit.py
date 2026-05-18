"""Token bucket rate limiter for CostSentinel."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class RateLimitDecision:
    """Result of a rate limit check."""

    allowed: bool
    remaining: int
    limit: int
    reset_at: float


class RateLimiter:
    """Token bucket rate limiter with per-scope limits.

    Supports global, per-user, and per-team rate limiting using a
    token bucket algorithm with configurable refill rates.
    """

    def __init__(
        self,
        global_rpm: int = 1000,
        per_user_rpm: int = 30,
        per_team_rpm: int = 200,
        storage_path: str | Path = ".costsentinel_ratelimit.json",
    ):
        """Initialize rate limiter.

        Args:
            global_rpm: Global requests per minute.
            per_user_rpm: Per-user requests per minute.
            per_team_rpm: Per-team requests per minute.
            storage_path: Path to JSON state file.
        """
        self.limits = {
            "global": global_rpm,
            "user": per_user_rpm,
            "team": per_team_rpm,
        }
        self.storage_path = Path(storage_path)
        self._state: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r") as f:
                    self._state = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._state = {}

    def _save(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, "w") as f:
            json.dump(self._state, f)

    def _get_bucket_key(self, scope: str, scope_id: str) -> str:
        return f"{scope}:{scope_id}"

    def _refill(self, key: str, scope: str) -> int:
        """Refill tokens based on elapsed time. Returns current token count."""
        now = time.time()
        limit = self.limits.get(scope, 30)
        tokens_per_second = limit / 60.0

        if key not in self._state:
            self._state[key] = {"tokens": limit, "last_refill": now}
            return limit

        bucket = self._state[key]
        elapsed = now - bucket["last_refill"]
        refill_amount = int(elapsed * tokens_per_second)

        if refill_amount > 0:
            bucket["tokens"] = min(limit, bucket["tokens"] + refill_amount)
            bucket["last_refill"] = now

        return bucket["tokens"]

    def check(self, scope: str, scope_id: str) -> RateLimitDecision:
        """Check if a request is allowed under rate limits.

        Args:
            scope: "global", "user", or "team".
            scope_id: Identifier for the scope (e.g., user_id).

        Returns:
            RateLimitDecision indicating if the request is allowed.
        """
        key = self._get_bucket_key(scope, scope_id)
        limit = self.limits.get(scope, 30)
        tokens = self._refill(key, scope)

        reset_at = time.time() + 60.0  # Approximate next full refill

        return RateLimitDecision(
            allowed=tokens > 0,
            remaining=max(0, tokens),
            limit=limit,
            reset_at=reset_at,
        )

    def consume(self, scope: str, scope_id: str) -> bool:
        """Consume a token from the bucket.

        Args:
            scope: "global", "user", or "team".
            scope_id: Identifier for the scope.

        Returns:
            True if token was consumed, False if bucket is empty.
        """
        key = self._get_bucket_key(scope, scope_id)
        self._refill(key, scope)

        bucket = self._state.get(key)
        if not bucket or bucket["tokens"] <= 0:
            self._save()
            return False

        bucket["tokens"] -= 1
        self._save()
        return True

    def get_remaining(self, scope: str, scope_id: str) -> int:
        """Get remaining tokens for a scope.

        Args:
            scope: "global", "user", or "team".
            scope_id: Identifier for the scope.

        Returns:
            Number of remaining tokens.
        """
        key = self._get_bucket_key(scope, scope_id)
        tokens = self._refill(key, scope)
        return max(0, tokens)
