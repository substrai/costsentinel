"""Chargeback report generation for cost allocation."""

from __future__ import annotations

import csv
import io
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ChargebackEntry:
    """A single chargeback line item."""

    team: str
    project: str
    endpoint: str
    model: str
    cost: float
    tokens: int
    request_count: int
    period: str  # e.g., "2025-05-18"


@dataclass
class ChargebackReport:
    """Complete chargeback report."""

    period_start: str
    period_end: str
    total_cost: float
    entries: List[ChargebackEntry]
    generated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "period_start": self.period_start,
            "period_end": self.period_end,
            "total_cost": self.total_cost,
            "generated_at": self.generated_at,
            "entries": [
                {
                    "team": e.team,
                    "project": e.project,
                    "endpoint": e.endpoint,
                    "model": e.model,
                    "cost": e.cost,
                    "tokens": e.tokens,
                    "request_count": e.request_count,
                    "period": e.period,
                }
                for e in self.entries
            ],
        }


class ChargebackGenerator:
    """Generates chargeback reports from attribution data.

    Aggregates costs by configurable dimensions (team, project, endpoint, model)
    and produces reports in multiple formats.
    """

    def __init__(
        self,
        attribution_path: str | Path = ".costsentinel_attributions.json",
        dimensions: Optional[List[str]] = None,
    ):
        """Initialize chargeback generator.

        Args:
            attribution_path: Path to attribution data file.
            dimensions: Dimensions to aggregate by. Default: [team, project, endpoint, model].
        """
        self.attribution_path = Path(attribution_path)
        self.dimensions = dimensions or ["team", "project", "endpoint", "model"]
        self._data: List[Dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if self.attribution_path.exists():
            try:
                with open(self.attribution_path, "r") as f:
                    raw = json.load(f)
                self._data = raw if isinstance(raw, list) else raw.get("records", [])
            except (json.JSONDecodeError, IOError):
                self._data = []

    def record(self, entry: Dict[str, Any]) -> None:
        """Record a cost attribution entry.

        Args:
            entry: Dict with team, project, endpoint, model, cost, tokens, timestamp.
        """
        if "timestamp" not in entry:
            entry["timestamp"] = time.time()
        self._data.append(entry)
        self._save()

    def _save(self) -> None:
        self.attribution_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.attribution_path, "w") as f:
            json.dump(self._data, f)

    def generate_report(
        self,
        period_days: int = 7,
        end_date: Optional[str] = None,
    ) -> ChargebackReport:
        """Generate a chargeback report for a time period.

        Args:
            period_days: Number of days to include.
            end_date: End date (YYYY-MM-DD). Defaults to today.

        Returns:
            ChargebackReport with aggregated entries.
        """
        now = datetime.now(timezone.utc)
        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            end_dt = now

        start_dt = end_dt - timedelta(days=period_days)
        start_ts = start_dt.timestamp()
        end_ts = end_dt.timestamp() + 86400  # Include full end day

        # Filter data to period
        period_data = [
            d for d in self._data
            if start_ts <= d.get("timestamp", 0) < end_ts
        ]

        # Aggregate by dimensions
        aggregated: Dict[str, Dict[str, Any]] = {}
        for record in period_data:
            key_parts = [record.get(dim, "unknown") for dim in self.dimensions]
            key = "|".join(key_parts)

            if key not in aggregated:
                aggregated[key] = {
                    "team": record.get("team", "unknown"),
                    "project": record.get("project", "default"),
                    "endpoint": record.get("endpoint", "unknown"),
                    "model": record.get("model", "unknown"),
                    "cost": 0.0,
                    "tokens": 0,
                    "request_count": 0,
                }

            aggregated[key]["cost"] += record.get("cost", 0.0)
            aggregated[key]["tokens"] += record.get("tokens", 0)
            aggregated[key]["request_count"] += 1

        entries = [
            ChargebackEntry(
                team=v["team"],
                project=v["project"],
                endpoint=v["endpoint"],
                model=v["model"],
                cost=round(v["cost"], 6),
                tokens=v["tokens"],
                request_count=v["request_count"],
                period=f"{start_dt.strftime('%Y-%m-%d')} to {end_dt.strftime('%Y-%m-%d')}",
            )
            for v in aggregated.values()
        ]

        # Sort by cost descending
        entries.sort(key=lambda e: e.cost, reverse=True)

        return ChargebackReport(
            period_start=start_dt.strftime("%Y-%m-%d"),
            period_end=end_dt.strftime("%Y-%m-%d"),
            total_cost=round(sum(e.cost for e in entries), 6),
            entries=entries,
        )

    def export_csv(self, report: ChargebackReport) -> str:
        """Export report as CSV string.

        Args:
            report: ChargebackReport to export.

        Returns:
            CSV-formatted string.
        """
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Team", "Project", "Endpoint", "Model", "Cost", "Tokens", "Requests", "Period"])
        for entry in report.entries:
            writer.writerow([
                entry.team, entry.project, entry.endpoint, entry.model,
                f"{entry.cost:.6f}", entry.tokens, entry.request_count, entry.period,
            ])
        return output.getvalue()

    def export_json(self, report: ChargebackReport) -> str:
        """Export report as JSON string."""
        return json.dumps(report.to_dict(), indent=2)

    def get_by_team(self, period_days: int = 30) -> Dict[str, float]:
        """Get cost breakdown by team.

        Args:
            period_days: Number of days to include.

        Returns:
            Dict mapping team name to total cost.
        """
        report = self.generate_report(period_days=period_days)
        by_team: Dict[str, float] = {}
        for entry in report.entries:
            by_team[entry.team] = by_team.get(entry.team, 0.0) + entry.cost
        return by_team
