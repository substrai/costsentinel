"""State management for cost tracking.

Stores running cost totals in a JSON file for development.
Production deployments should use DynamoDB or similar.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, Optional


def _get_period_key(period: str) -> str:
    """Get the current period key for bucketing costs.

    Args:
        period: "daily" or "monthly".

    Returns:
        A string key like "2024-01-15" (daily) or "2024-01" (monthly).
    """
    now = datetime.now(timezone.utc)
    if period == "daily":
        return now.strftime("%Y-%m-%d")
    elif period == "monthly":
        return now.strftime("%Y-%m")
    else:
        raise ValueError(f"Invalid period '{period}'. Must be 'daily' or 'monthly'.")


@contextmanager
def _file_lock(lock_path: str) -> Generator[None, None, None]:
    """Cross-platform file locking context manager.

    Uses fcntl on Unix systems and a simple lock file on Windows.
    """
    if sys.platform == "win32":
        # Windows fallback: use a .lock file
        lock_file = lock_path + ".lock"
        while True:
            try:
                fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                break
            except FileExistsError:
                import time
                time.sleep(0.01)
        try:
            yield
        finally:
            try:
                os.unlink(lock_file)
            except OSError:
                pass
    else:
        import fcntl
        lock_file = lock_path + ".lock"
        fd = open(lock_file, "w")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            fd.close()


class CostState:
    """Manages running cost totals with file-based persistence.

    Thread-safe via threading lock + file locking for multi-process safety.

    State structure:
    {
        "global": {
            "default": {"daily": {"2024-01-15": 12.50}, "monthly": {"2024-01": 150.00}}
        },
        "team": {
            "team-alpha": {"daily": {"2024-01-15": 5.00}, "monthly": {"2024-01": 60.00}}
        },
        ...
    }
    """

    VALID_SCOPES = ("global", "team", "endpoint", "user")

    def __init__(self, state_file: str = "costsentinel_state.json"):
        """Initialize state manager.

        Args:
            state_file: Path to the JSON state file.
        """
        self._state_file = state_file
        self._lock = threading.Lock()
        self._ensure_state_file()

    @property
    def state_file(self) -> str:
        """Path to the state file."""
        return self._state_file

    def _ensure_state_file(self) -> None:
        """Create state file if it doesn't exist."""
        path = Path(self._state_file)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            self._write_state({})

    def _read_state(self) -> Dict[str, Any]:
        """Read state from file."""
        try:
            with open(self._state_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _write_state(self, state: Dict[str, Any]) -> None:
        """Write state to file."""
        with open(self._state_file, "w") as f:
            json.dump(state, f, indent=2)

    def _validate_scope(self, scope: str) -> None:
        """Validate scope value."""
        if scope not in self.VALID_SCOPES:
            raise ValueError(
                f"Invalid scope '{scope}'. Must be one of {self.VALID_SCOPES}."
            )

    def increment(self, scope: str, scope_id: str, amount: float) -> float:
        """Increment cost total for a scope.

        Args:
            scope: One of "global", "team", "endpoint", "user".
            scope_id: Identifier within the scope (e.g., team name, user ID).
            amount: Cost amount to add (USD).

        Returns:
            New total for the current daily period.
        """
        self._validate_scope(scope)

        with self._lock:
            with _file_lock(self._state_file):
                state = self._read_state()

                if scope not in state:
                    state[scope] = {}
                if scope_id not in state[scope]:
                    state[scope][scope_id] = {"daily": {}, "monthly": {}}

                entry = state[scope][scope_id]

                # Increment daily
                daily_key = _get_period_key("daily")
                entry["daily"][daily_key] = entry["daily"].get(daily_key, 0.0) + amount

                # Increment monthly
                monthly_key = _get_period_key("monthly")
                entry["monthly"][monthly_key] = (
                    entry["monthly"].get(monthly_key, 0.0) + amount
                )

                self._write_state(state)
                return entry["daily"][daily_key]

    def get_total(
        self, scope: str, scope_id: str, period: str = "daily"
    ) -> float:
        """Get the current cost total for a scope.

        Args:
            scope: One of "global", "team", "endpoint", "user".
            scope_id: Identifier within the scope.
            period: "daily" or "monthly".

        Returns:
            Current total for the specified period, or 0.0 if no data.
        """
        self._validate_scope(scope)

        with self._lock:
            with _file_lock(self._state_file):
                state = self._read_state()

        period_key = _get_period_key(period)

        try:
            return state[scope][scope_id][period][period_key]
        except KeyError:
            return 0.0

    def get_all_totals(self, scope: str) -> Dict[str, Dict[str, float]]:
        """Get all totals for a scope.

        Args:
            scope: One of "global", "team", "endpoint", "user".

        Returns:
            Dict mapping scope_ids to {"daily": amount, "monthly": amount}.
        """
        self._validate_scope(scope)

        with self._lock:
            with _file_lock(self._state_file):
                state = self._read_state()

        result = {}
        daily_key = _get_period_key("daily")
        monthly_key = _get_period_key("monthly")

        for scope_id, data in state.get(scope, {}).items():
            result[scope_id] = {
                "daily": data.get("daily", {}).get(daily_key, 0.0),
                "monthly": data.get("monthly", {}).get(monthly_key, 0.0),
            }

        return result

    def reset(self, scope: str, scope_id: str) -> None:
        """Reset cost totals for a scope.

        Args:
            scope: One of "global", "team", "endpoint", "user".
            scope_id: Identifier within the scope.
        """
        self._validate_scope(scope)

        with self._lock:
            with _file_lock(self._state_file):
                state = self._read_state()

                if scope in state and scope_id in state[scope]:
                    state[scope][scope_id] = {"daily": {}, "monthly": {}}
                    self._write_state(state)

    def reset_all(self) -> None:
        """Reset all state data."""
        with self._lock:
            with _file_lock(self._state_file):
                self._write_state({})
