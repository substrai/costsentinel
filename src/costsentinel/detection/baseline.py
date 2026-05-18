"""Baseline learning for normal spending patterns."""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class BaselineMetrics:
    """Baseline metrics for a scope."""

    mean_cost_per_hour: float = 0.0
    std_cost_per_hour: float = 0.0
    mean_requests_per_hour: float = 0.0
    mean_tokens_per_request: float = 0.0
    sample_count: int = 0
    last_updated: float = 0.0


class BaselineLearner:
    """Learns normal spending patterns from historical data.

    Computes rolling statistics (mean, std) for cost rates per scope,
    used by the anomaly detector to identify deviations.
    """

    def __init__(
        self,
        window_days: int = 7,
        storage_path: str | Path = ".costsentinel_baselines.json",
    ):
        self.window_days = window_days
        self.storage_path = Path(storage_path)
        self._baselines: Dict[str, BaselineMetrics] = {}
        self._history: Dict[str, List[Dict[str, Any]]] = {}
        self._load()

    def _load(self) -> None:
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r") as f:
                    data = json.load(f)
                for key, val in data.get("baselines", {}).items():
                    self._baselines[key] = BaselineMetrics(**val)
                self._history = data.get("history", {})
            except (json.JSONDecodeError, IOError):
                pass

    def _save(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "baselines": {k: vars(v) for k, v in self._baselines.items()},
            "history": self._history,
        }
        with open(self.storage_path, "w") as f:
            json.dump(data, f)

    def record(self, scope_key: str, cost: float, tokens: int) -> None:
        """Record a data point for baseline learning.

        Args:
            scope_key: Identifier (e.g., "user:user-1", "endpoint:/api/chat").
            cost: Cost of the request.
            tokens: Total tokens used.
        """
        now = time.time()
        if scope_key not in self._history:
            self._history[scope_key] = []

        self._history[scope_key].append({
            "timestamp": now,
            "cost": cost,
            "tokens": tokens,
        })

        # Prune old entries beyond window
        cutoff = now - (self.window_days * 86400)
        self._history[scope_key] = [
            e for e in self._history[scope_key] if e["timestamp"] >= cutoff
        ]

        self._recompute(scope_key)
        self._save()

    def _recompute(self, scope_key: str) -> None:
        """Recompute baseline metrics from history."""
        entries = self._history.get(scope_key, [])
        if not entries:
            return

        now = time.time()
        # Group by hour
        hourly_costs: Dict[int, float] = {}
        hourly_requests: Dict[int, int] = {}
        total_tokens = 0

        for entry in entries:
            hour_bucket = int(entry["timestamp"] // 3600)
            hourly_costs[hour_bucket] = hourly_costs.get(hour_bucket, 0.0) + entry["cost"]
            hourly_requests[hour_bucket] = hourly_requests.get(hour_bucket, 0) + 1
            total_tokens += entry["tokens"]

        costs = list(hourly_costs.values())
        requests = list(hourly_requests.values())

        mean_cost = sum(costs) / len(costs) if costs else 0.0
        std_cost = math.sqrt(sum((c - mean_cost) ** 2 for c in costs) / max(len(costs), 1))
        mean_requests = sum(requests) / len(requests) if requests else 0.0
        mean_tokens = total_tokens / len(entries) if entries else 0.0

        self._baselines[scope_key] = BaselineMetrics(
            mean_cost_per_hour=mean_cost,
            std_cost_per_hour=std_cost,
            mean_requests_per_hour=mean_requests,
            mean_tokens_per_request=mean_tokens,
            sample_count=len(entries),
            last_updated=now,
        )

    def get_baseline(self, scope_key: str) -> Optional[BaselineMetrics]:
        """Get baseline metrics for a scope.

        Args:
            scope_key: The scope identifier.

        Returns:
            BaselineMetrics or None if no baseline exists.
        """
        return self._baselines.get(scope_key)

    def refresh(self) -> None:
        """Recompute all baselines from history."""
        for key in list(self._history.keys()):
            self._recompute(key)
        self._save()

    def has_baseline(self, scope_key: str) -> bool:
        """Check if a baseline exists for a scope."""
        baseline = self._baselines.get(scope_key)
        return baseline is not None and baseline.sample_count >= 10
