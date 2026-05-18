"""Cost attribution tracking for LLM API calls."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from costsentinel.core.state import _file_lock, _get_period_key


@dataclass
class CostAttribution:
    """A single cost attribution record."""

    user_id: str
    team_id: str
    endpoint: str
    model: str
    timestamp: str
    cost: float
    tokens_in: int
    tokens_out: int


class AttributionStore:
    """Stores and queries cost attribution records.

    Uses a JSON file for persistence in development.
    Production deployments should use a proper database.
    """

    def __init__(self, attribution_file: str = "costsentinel_attributions.json"):
        """Initialize attribution store.

        Args:
            attribution_file: Path to the JSON attribution file.
        """
        self._file = attribution_file
        self._lock = threading.Lock()
        self._ensure_file()

    @property
    def attribution_file(self) -> str:
        """Path to the attribution file."""
        return self._file

    def _ensure_file(self) -> None:
        """Create attribution file if it doesn't exist."""
        path = Path(self._file)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            self._write_records([])

    def _read_records(self) -> List[Dict[str, Any]]:
        """Read all attribution records."""
        try:
            with open(self._file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _write_records(self, records: List[Dict[str, Any]]) -> None:
        """Write attribution records."""
        with open(self._file, "w") as f:
            json.dump(records, f, indent=2)

    def record(self, attribution: CostAttribution) -> None:
        """Record a cost attribution.

        Args:
            attribution: The attribution record to store.
        """
        with self._lock:
            with _file_lock(self._file):
                records = self._read_records()
                records.append(asdict(attribution))
                self._write_records(records)

    def get_by_team(
        self, team_id: str, period: str = "daily"
    ) -> List[CostAttribution]:
        """Get attributions for a team within a period.

        Args:
            team_id: Team identifier.
            period: "daily" or "monthly".

        Returns:
            List of matching attribution records.
        """
        return self._filter_records("team_id", team_id, period)

    def get_by_user(
        self, user_id: str, period: str = "daily"
    ) -> List[CostAttribution]:
        """Get attributions for a user within a period.

        Args:
            user_id: User identifier.
            period: "daily" or "monthly".

        Returns:
            List of matching attribution records.
        """
        return self._filter_records("user_id", user_id, period)

    def get_by_endpoint(
        self, endpoint: str, period: str = "daily"
    ) -> List[CostAttribution]:
        """Get attributions for an endpoint within a period.

        Args:
            endpoint: Endpoint identifier.
            period: "daily" or "monthly".

        Returns:
            List of matching attribution records.
        """
        return self._filter_records("endpoint", endpoint, period)

    def get_summary(self, period: str = "daily") -> Dict[str, Any]:
        """Get a summary of all attributions for a period.

        Args:
            period: "daily" or "monthly".

        Returns:
            Summary dict with total_cost, total_calls, by_model, by_team, by_user.
        """
        records = self._get_period_records(period)

        summary: Dict[str, Any] = {
            "total_cost": 0.0,
            "total_calls": len(records),
            "total_tokens_in": 0,
            "total_tokens_out": 0,
            "by_model": {},
            "by_team": {},
            "by_user": {},
            "by_endpoint": {},
        }

        for record in records:
            cost = record["cost"]
            summary["total_cost"] += cost
            summary["total_tokens_in"] += record["tokens_in"]
            summary["total_tokens_out"] += record["tokens_out"]

            # By model
            model = record["model"]
            if model not in summary["by_model"]:
                summary["by_model"][model] = {"cost": 0.0, "calls": 0}
            summary["by_model"][model]["cost"] += cost
            summary["by_model"][model]["calls"] += 1

            # By team
            team = record["team_id"]
            if team not in summary["by_team"]:
                summary["by_team"][team] = {"cost": 0.0, "calls": 0}
            summary["by_team"][team]["cost"] += cost
            summary["by_team"][team]["calls"] += 1

            # By user
            user = record["user_id"]
            if user not in summary["by_user"]:
                summary["by_user"][user] = {"cost": 0.0, "calls": 0}
            summary["by_user"][user]["cost"] += cost
            summary["by_user"][user]["calls"] += 1

            # By endpoint
            endpoint = record["endpoint"]
            if endpoint not in summary["by_endpoint"]:
                summary["by_endpoint"][endpoint] = {"cost": 0.0, "calls": 0}
            summary["by_endpoint"][endpoint]["cost"] += cost
            summary["by_endpoint"][endpoint]["calls"] += 1

        return summary

    def _filter_records(
        self, field: str, value: str, period: str
    ) -> List[CostAttribution]:
        """Filter records by field value within a period."""
        records = self._get_period_records(period)
        return [
            CostAttribution(**record)
            for record in records
            if record.get(field) == value
        ]

    def _get_period_records(self, period: str) -> List[Dict[str, Any]]:
        """Get records within the current period."""
        with self._lock:
            with _file_lock(self._file):
                records = self._read_records()

        period_key = _get_period_key(period)

        filtered = []
        for record in records:
            ts = record.get("timestamp", "")
            if period == "daily" and ts[:10] == period_key:
                filtered.append(record)
            elif period == "monthly" and ts[:7] == period_key:
                filtered.append(record)

        return filtered

    def clear(self) -> None:
        """Clear all attribution records."""
        with self._lock:
            with _file_lock(self._file):
                self._write_records([])
