"""Cost reporting for CostSentinel."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from costsentinel.core.config import CostSentinelConfig
from costsentinel.core.state import CostState
from costsentinel.policies.attribution import AttributionStore


class CostReporter:
    """Generates cost reports from state and attribution data.

    Provides breakdowns by model, team, endpoint, and user
    for daily and monthly periods.
    """

    def __init__(
        self,
        config: CostSentinelConfig,
        state: Optional[CostState] = None,
        attribution: Optional[AttributionStore] = None,
    ):
        """Initialize reporter.

        Args:
            config: CostSentinel configuration.
            state: Cost state store. Created from config if None.
            attribution: Attribution store. Created from config if None.
        """
        self._config = config
        self._state = state or CostState(config.state_file)
        self._attribution = attribution or AttributionStore(config.attribution_file)

    def daily_report(self) -> Dict[str, Any]:
        """Generate today's cost report.

        Returns:
            Dict with costs broken down by scope.
        """
        return {
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "global": self._state.get_all_totals("global"),
            "teams": self._state.get_all_totals("team"),
            "endpoints": self._state.get_all_totals("endpoint"),
            "users": self._state.get_all_totals("user"),
            "summary": self._attribution.get_summary("daily"),
        }

    def breakdown_by_model(self, period: str = "daily") -> Dict[str, Any]:
        """Get cost breakdown by model.

        Args:
            period: "daily" or "monthly".

        Returns:
            Dict mapping model names to cost and call count.
        """
        summary = self._attribution.get_summary(period)
        return summary.get("by_model", {})

    def breakdown_by_team(self, period: str = "daily") -> Dict[str, Any]:
        """Get cost breakdown by team.

        Args:
            period: "daily" or "monthly".

        Returns:
            Dict mapping team IDs to cost and call count.
        """
        summary = self._attribution.get_summary(period)
        return summary.get("by_team", {})

    def breakdown_by_endpoint(self, period: str = "daily") -> Dict[str, Any]:
        """Get cost breakdown by endpoint.

        Args:
            period: "daily" or "monthly".

        Returns:
            Dict mapping endpoints to cost and call count.
        """
        summary = self._attribution.get_summary(period)
        return summary.get("by_endpoint", {})

    def top_users(self, n: int = 10, period: str = "daily") -> List[Dict[str, Any]]:
        """Get the highest-spending users.

        Args:
            n: Number of top users to return.
            period: "daily" or "monthly".

        Returns:
            List of dicts with user_id, cost, and calls, sorted by cost descending.
        """
        summary = self._attribution.get_summary(period)
        by_user = summary.get("by_user", {})

        users = [
            {"user_id": uid, "cost": data["cost"], "calls": data["calls"]}
            for uid, data in by_user.items()
        ]
        users.sort(key=lambda x: x["cost"], reverse=True)
        return users[:n]

    def format_report(
        self, report_data: Optional[Dict[str, Any]] = None, format: str = "text"
    ) -> str:
        """Format a report for human-readable output.

        Args:
            report_data: Report data dict. If None, generates daily report.
            format: Output format ("text" or "json").

        Returns:
            Formatted report string.
        """
        if report_data is None:
            report_data = self.daily_report()

        if format == "json":
            import json
            return json.dumps(report_data, indent=2, default=str)

        return self._format_text(report_data)

    def _format_text(self, report_data: Dict[str, Any]) -> str:
        """Format report as human-readable text."""
        lines = []
        lines.append("=" * 60)
        lines.append("  CostSentinel Daily Report")
        lines.append(f"  Date: {report_data.get('date', 'N/A')}")
        lines.append("=" * 60)

        summary = report_data.get("summary", {})
        lines.append("")
        lines.append(f"  Total Cost:    ${summary.get('total_cost', 0):.4f}")
        lines.append(f"  Total Calls:   {summary.get('total_calls', 0)}")
        lines.append(f"  Tokens In:     {summary.get('total_tokens_in', 0):,}")
        lines.append(f"  Tokens Out:    {summary.get('total_tokens_out', 0):,}")

        # By model
        by_model = summary.get("by_model", {})
        if by_model:
            lines.append("")
            lines.append("  --- By Model ---")
            for model, data in sorted(by_model.items(), key=lambda x: x[1]["cost"], reverse=True):
                lines.append(f"  {model:<25} ${data['cost']:.4f}  ({data['calls']} calls)")

        # By team
        by_team = summary.get("by_team", {})
        if by_team:
            lines.append("")
            lines.append("  --- By Team ---")
            for team, data in sorted(by_team.items(), key=lambda x: x[1]["cost"], reverse=True):
                lines.append(f"  {team:<25} ${data['cost']:.4f}  ({data['calls']} calls)")

        # By endpoint
        by_endpoint = summary.get("by_endpoint", {})
        if by_endpoint:
            lines.append("")
            lines.append("  --- By Endpoint ---")
            for ep, data in sorted(by_endpoint.items(), key=lambda x: x[1]["cost"], reverse=True):
                lines.append(f"  {ep:<25} ${data['cost']:.4f}  ({data['calls']} calls)")

        # Top users
        by_user = summary.get("by_user", {})
        if by_user:
            lines.append("")
            lines.append("  --- Top Users ---")
            sorted_users = sorted(by_user.items(), key=lambda x: x[1]["cost"], reverse=True)[:10]
            for user, data in sorted_users:
                lines.append(f"  {user:<25} ${data['cost']:.4f}  ({data['calls']} calls)")

        lines.append("")
        lines.append("=" * 60)
        return "\n".join(lines)
