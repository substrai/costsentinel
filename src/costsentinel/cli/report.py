"""CLI command for cost reporting with time range and scope filtering.

Generates cost reports filtered by time period, team, endpoint, or user.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


@dataclass
class ReportFilter:
    """Filters for cost report generation."""

    period: str = "7d"  # e.g., "7d", "30d", "24h", "1h"
    team: Optional[str] = None
    endpoint: Optional[str] = None
    user: Optional[str] = None
    model: Optional[str] = None

    @property
    def start_time(self) -> datetime:
        """Calculate start time from period string."""
        now = datetime.now(timezone.utc)
        value = int(self.period[:-1])
        unit = self.period[-1]
        if unit == "d":
            return now - timedelta(days=value)
        elif unit == "h":
            return now - timedelta(hours=value)
        elif unit == "m":
            return now - timedelta(minutes=value)
        else:
            raise ValueError(f"Invalid period unit '{unit}'. Use 'd', 'h', or 'm'.")


@dataclass
class ReportEntry:
    """A single entry in the cost report."""

    scope: str
    scope_id: str
    daily_cost: float
    monthly_cost: float
    request_count: int = 0
    avg_cost_per_request: float = 0.0
    top_model: str = ""
    budget_utilization: float = 0.0


@dataclass
class CostReport:
    """Generated cost report."""

    title: str
    period: str
    generated_at: str
    filters: Dict[str, Any]
    entries: List[ReportEntry] = field(default_factory=list)
    total_cost: float = 0.0
    total_requests: int = 0
    avg_daily_cost: float = 0.0
    projected_monthly: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary."""
        return {
            "title": self.title,
            "period": self.period,
            "generated_at": self.generated_at,
            "filters": self.filters,
            "summary": {
                "total_cost": round(self.total_cost, 4),
                "total_requests": self.total_requests,
                "avg_daily_cost": round(self.avg_daily_cost, 4),
                "projected_monthly": round(self.projected_monthly, 4),
            },
            "entries": [
                {
                    "scope": e.scope,
                    "scope_id": e.scope_id,
                    "daily_cost": round(e.daily_cost, 4),
                    "monthly_cost": round(e.monthly_cost, 4),
                    "request_count": e.request_count,
                    "avg_cost_per_request": round(e.avg_cost_per_request, 4),
                    "top_model": e.top_model,
                    "budget_utilization": round(e.budget_utilization, 2),
                }
                for e in self.entries
            ],
        }

    def to_text(self) -> str:
        """Render report as formatted text."""
        lines = [
            f"{'=' * 60}",
            f"  {self.title}",
            f"  Period: {self.period} | Generated: {self.generated_at}",
            f"{'=' * 60}",
            "",
            f"  Total Cost:        ${self.total_cost:.4f}",
            f"  Total Requests:    {self.total_requests}",
            f"  Avg Daily Cost:    ${self.avg_daily_cost:.4f}",
            f"  Projected Monthly: ${self.projected_monthly:.4f}",
            "",
            f"{'─' * 60}",
            f"  {'Scope':<15} {'ID':<20} {'Daily':<10} {'Monthly':<10} {'Reqs':<6}",
            f"{'─' * 60}",
        ]
        for e in self.entries:
            lines.append(
                f"  {e.scope:<15} {e.scope_id:<20} ${e.daily_cost:<9.4f} ${e.monthly_cost:<9.4f} {e.request_count:<6}"
            )
        lines.append(f"{'─' * 60}")
        return "\n".join(lines)


def generate_report(
    state,
    report_filter: Optional[ReportFilter] = None,
    config=None,
) -> CostReport:
    """Generate a cost report from state data.

    Args:
        state: CostState or DynamoDBCostState instance.
        report_filter: Optional filters for the report.
        config: Optional CostSentinelConfig for budget utilization.

    Returns:
        CostReport with filtered and aggregated data.
    """
    if report_filter is None:
        report_filter = ReportFilter()

    now = datetime.now(timezone.utc)
    filters_dict = {
        "period": report_filter.period,
        "team": report_filter.team,
        "endpoint": report_filter.endpoint,
        "user": report_filter.user,
        "model": report_filter.model,
    }

    entries: List[ReportEntry] = []
    total_cost = 0.0

    # Determine which scopes to query
    scopes_to_query = []
    if report_filter.team:
        scopes_to_query.append(("team", report_filter.team))
    elif report_filter.endpoint:
        scopes_to_query.append(("endpoint", report_filter.endpoint))
    elif report_filter.user:
        scopes_to_query.append(("user", report_filter.user))
    else:
        # Query all scopes
        for scope in ("global", "team", "endpoint", "user"):
            totals = state.get_all_totals(scope)
            for scope_id, costs in totals.items():
                daily = costs.get("daily", 0.0)
                monthly = costs.get("monthly", 0.0)
                total_cost += daily

                budget_util = 0.0
                if config:
                    policy = config.get_policy(scope)
                    if policy and policy.limit_daily and policy.limit_daily > 0:
                        budget_util = (daily / policy.limit_daily) * 100

                entries.append(ReportEntry(
                    scope=scope,
                    scope_id=scope_id,
                    daily_cost=daily,
                    monthly_cost=monthly,
                    budget_utilization=budget_util,
                ))

    # For specific scope queries
    for scope, scope_id in scopes_to_query:
        daily = state.get_total(scope, scope_id, "daily")
        monthly = state.get_total(scope, scope_id, "monthly")
        total_cost += daily
        entries.append(ReportEntry(
            scope=scope,
            scope_id=scope_id,
            daily_cost=daily,
            monthly_cost=monthly,
        ))

    # Sort by daily cost descending
    entries.sort(key=lambda e: e.daily_cost, reverse=True)

    # Calculate projections
    period_days = int(report_filter.period[:-1]) if report_filter.period.endswith("d") else 1
    avg_daily = total_cost / max(period_days, 1)
    projected_monthly = avg_daily * 30

    return CostReport(
        title=f"CostSentinel Report — Last {report_filter.period}",
        period=report_filter.period,
        generated_at=now.isoformat(),
        filters={k: v for k, v in filters_dict.items() if v},
        entries=entries,
        total_cost=total_cost,
        total_requests=sum(e.request_count for e in entries),
        avg_daily_cost=avg_daily,
        projected_monthly=projected_monthly,
    )
