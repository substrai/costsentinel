"""Circuit breaker for expensive requests and runaway sessions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


class CircuitBreakerTripped(Exception):
    """Raised when a circuit breaker threshold is exceeded."""

    def __init__(self, message: str, threshold: float, current: float):
        super().__init__(message)
        self.threshold = threshold
        self.current = current


@dataclass
class CircuitDecision:
    """Result of a circuit breaker check."""

    allowed: bool
    reason: str
    threshold: float
    current: float


class CircuitBreaker:
    """Kills expensive requests and runaway sessions.

    Enforces per-request cost limits, per-session cumulative cost limits,
    and per-request token limits to prevent cost explosions.
    """

    def __init__(
        self,
        max_cost_per_request: float = 0.50,
        max_cost_per_session: float = 5.00,
        max_tokens_per_request: int = 8000,
        storage_path: str | Path = ".costsentinel_circuits.json",
    ):
        """Initialize circuit breaker.

        Args:
            max_cost_per_request: Maximum allowed cost for a single request.
            max_cost_per_session: Maximum cumulative cost for a session.
            max_tokens_per_request: Maximum input tokens for a single request.
            storage_path: Path to JSON state file for session tracking.
        """
        self.max_cost_per_request = max_cost_per_request
        self.max_cost_per_session = max_cost_per_session
        self.max_tokens_per_request = max_tokens_per_request
        self.storage_path = Path(storage_path)
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r") as f:
                    self._sessions = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._sessions = {}

    def _save(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, "w") as f:
            json.dump(self._sessions, f)

    def check_request(
        self, estimated_cost: float = 0.0, input_tokens: int = 0
    ) -> CircuitDecision:
        """Check if a single request should be allowed.

        Args:
            estimated_cost: Estimated cost of the request.
            input_tokens: Number of input tokens.

        Returns:
            CircuitDecision indicating if the request is allowed.
        """
        # Check cost limit
        if estimated_cost > self.max_cost_per_request:
            return CircuitDecision(
                allowed=False,
                reason=f"Request cost ${estimated_cost:.4f} exceeds limit ${self.max_cost_per_request:.4f}",
                threshold=self.max_cost_per_request,
                current=estimated_cost,
            )

        # Check token limit
        if input_tokens > self.max_tokens_per_request:
            return CircuitDecision(
                allowed=False,
                reason=f"Input tokens {input_tokens} exceeds limit {self.max_tokens_per_request}",
                threshold=float(self.max_tokens_per_request),
                current=float(input_tokens),
            )

        return CircuitDecision(
            allowed=True,
            reason="Within limits",
            threshold=self.max_cost_per_request,
            current=estimated_cost,
        )

    def check_session(self, session_id: str) -> CircuitDecision:
        """Check if a session has exceeded its cost limit.

        Args:
            session_id: The session identifier.

        Returns:
            CircuitDecision indicating if the session is allowed to continue.
        """
        session = self._sessions.get(session_id, {})
        total_cost = session.get("total_cost", 0.0)

        if total_cost >= self.max_cost_per_session:
            return CircuitDecision(
                allowed=False,
                reason=f"Session cost ${total_cost:.4f} exceeds limit ${self.max_cost_per_session:.4f}",
                threshold=self.max_cost_per_session,
                current=total_cost,
            )

        return CircuitDecision(
            allowed=True,
            reason="Session within limits",
            threshold=self.max_cost_per_session,
            current=total_cost,
        )

    def record_session_cost(self, session_id: str, cost: float) -> None:
        """Record cost for a session.

        Args:
            session_id: The session identifier.
            cost: Cost to add to the session total.
        """
        if session_id not in self._sessions:
            self._sessions[session_id] = {"total_cost": 0.0, "request_count": 0}

        self._sessions[session_id]["total_cost"] += cost
        self._sessions[session_id]["request_count"] += 1
        self._save()

    def get_session_cost(self, session_id: str) -> float:
        """Get total cost for a session.

        Args:
            session_id: The session identifier.

        Returns:
            Total accumulated cost for the session.
        """
        return self._sessions.get(session_id, {}).get("total_cost", 0.0)

    def reset_session(self, session_id: str) -> None:
        """Reset a session's cost tracking.

        Args:
            session_id: The session identifier.
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
            self._save()
