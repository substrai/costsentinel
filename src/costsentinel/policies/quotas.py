"""Token quota enforcement - daily token limits per user."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class QuotaDecision:
    """Result of a quota check."""

    allowed: bool
    used: int
    limit: int
    remaining: int


class TokenQuotaEnforcer:
    """Enforces per-user daily token quotas (separate from cost budgets).

    Tracks total tokens consumed per user per day and blocks requests
    that would exceed the configured limit.
    """

    def __init__(
        self,
        default_daily_limit: int = 100000,
        user_limits: Optional[Dict[str, int]] = None,
        storage_path: str | Path = ".costsentinel_quotas.json",
    ):
        """Initialize token quota enforcer.

        Args:
            default_daily_limit: Default daily token limit per user.
            user_limits: Optional per-user overrides {user_id: limit}.
            storage_path: Path to JSON state file.
        """
        self.default_daily_limit = default_daily_limit
        self.user_limits = user_limits or {}
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

    def _get_today(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _get_user_state(self, user_id: str) -> Dict[str, Any]:
        today = self._get_today()
        if user_id not in self._state or self._state[user_id].get("date") != today:
            self._state[user_id] = {"date": today, "tokens_used": 0}
        return self._state[user_id]

    def _get_limit(self, user_id: str) -> int:
        return self.user_limits.get(user_id, self.default_daily_limit)

    def check_quota(self, user_id: str, estimated_tokens: int = 0) -> QuotaDecision:
        """Check if a user has quota remaining.

        Args:
            user_id: The user identifier.
            estimated_tokens: Estimated tokens for the upcoming request.

        Returns:
            QuotaDecision indicating if the request is allowed.
        """
        state = self._get_user_state(user_id)
        limit = self._get_limit(user_id)
        used = state["tokens_used"]
        remaining = max(0, limit - used)

        allowed = (used + estimated_tokens) <= limit

        return QuotaDecision(
            allowed=allowed,
            used=used,
            limit=limit,
            remaining=remaining,
        )

    def record_usage(self, user_id: str, tokens: int) -> None:
        """Record token usage for a user.

        Args:
            user_id: The user identifier.
            tokens: Number of tokens consumed.
        """
        state = self._get_user_state(user_id)
        state["tokens_used"] += tokens
        self._save()

    def get_usage(self, user_id: str) -> Dict[str, Any]:
        """Get current usage for a user.

        Args:
            user_id: The user identifier.

        Returns:
            Dict with used, limit, remaining, and date.
        """
        state = self._get_user_state(user_id)
        limit = self._get_limit(user_id)
        used = state["tokens_used"]
        return {
            "user_id": user_id,
            "used": used,
            "limit": limit,
            "remaining": max(0, limit - used),
            "date": state["date"],
        }
