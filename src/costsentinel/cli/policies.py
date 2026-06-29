"""CLI command for policy simulation and testing.

Provides 'costsentinel policies test --simulate' to dry-run policy
enforcement against historical data without affecting actual budgets.

Usage:
    costsentinel policies test --simulate
    costsentinel policies test --simulate --config costsentinel.yaml --data costs.json
    costsentinel policies test --simulate --scope team --id engineering
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class SimulationRequest:
    """A simulated cost request for policy testing."""

    model: str
    input_tokens: int
    output_tokens: int
    cost: float
    user_id: Optional[str] = None
    team_id: Optional[str] = None
    endpoint: Optional[str] = None
    timestamp: Optional[float] = None


@dataclass
class PolicyDecision:
    """Result of a policy evaluation."""

    allowed: bool
    action: str  # "allow", "block", "downgrade", "alert"
    scope: str
    scope_id: str
    reason: str
    budget_used: float
    budget_limit: float
    utilization_percent: float


@dataclass
class SimulationResult:
    """Result of a single request simulation."""

    request_index: int
    request: SimulationRequest
    decisions: List[PolicyDecision]
    final_action: str  # The most restrictive action
    would_be_blocked: bool
    would_be_downgraded: bool


@dataclass
class SimulationReport:
    """Complete simulation report."""

    total_requests: int
    blocked_count: int
    downgraded_count: int
    alerted_count: int
    allowed_count: int
    total_cost_simulated: float
    policy_violations: List[SimulationResult]
    scope_utilization: Dict[str, Dict[str, float]]  # scope -> id -> utilization%
    recommendations: List[str]

    @property
    def block_rate(self) -> float:
        """Percentage of requests that would be blocked."""
        if self.total_requests == 0:
            return 0.0
        return self.blocked_count / self.total_requests * 100

    @property
    def pass_rate(self) -> float:
        """Percentage of requests that would pass."""
        if self.total_requests == 0:
            return 100.0
        return self.allowed_count / self.total_requests * 100


class PolicySimulator:
    """Simulates policy enforcement against historical or synthetic data.

    Dry-runs budget policies without modifying actual state, showing
    what would happen if the policies were applied to the provided data.

    Args:
        policies: Policy configuration dictionary.
        pricing: Model pricing configuration.
    """

    def __init__(
        self,
        policies: Optional[Dict[str, Any]] = None,
        pricing: Optional[Dict[str, Dict[str, float]]] = None,
    ):
        self._policies = policies or {
            "global": {"limit_daily": 100.0, "on_exceed": "block"},
            "team": {"limit_daily": 25.0, "on_exceed": "downgrade"},
            "user": {"limit_daily": 5.0, "on_exceed": "block", "max_cost_per_request": 0.50},
        }
        self._pricing = pricing or {}
        self._cumulative: Dict[str, Dict[str, float]] = {}

    def simulate(self, requests: List[SimulationRequest]) -> SimulationReport:
        """Run a full simulation against a list of requests.

        Args:
            requests: Historical or synthetic cost requests to simulate.

        Returns:
            SimulationReport with detailed results.
        """
        self._cumulative = {}
        results: List[SimulationResult] = []
        violations: List[SimulationResult] = []

        blocked = 0
        downgraded = 0
        alerted = 0
        allowed = 0
        total_cost = 0.0

        for i, request in enumerate(requests):
            result = self._simulate_request(i, request)
            results.append(result)
            total_cost += request.cost

            if result.would_be_blocked:
                blocked += 1
                violations.append(result)
            elif result.would_be_downgraded:
                downgraded += 1
                violations.append(result)
            elif result.final_action == "alert":
                alerted += 1
            else:
                allowed += 1

            # Accumulate costs for tracking
            self._accumulate(request)

        # Calculate utilization
        utilization = self._compute_utilization()

        # Generate recommendations
        recommendations = self._generate_recommendations(
            blocked, downgraded, total_cost, len(requests), utilization
        )

        return SimulationReport(
            total_requests=len(requests),
            blocked_count=blocked,
            downgraded_count=downgraded,
            alerted_count=alerted,
            allowed_count=allowed,
            total_cost_simulated=total_cost,
            policy_violations=violations,
            scope_utilization=utilization,
            recommendations=recommendations,
        )

    def _simulate_request(self, index: int, request: SimulationRequest) -> SimulationResult:
        """Simulate a single request against all applicable policies."""
        decisions: List[PolicyDecision] = []

        # Check user policy
        if request.user_id and "user" in self._policies:
            decision = self._check_scope("user", request.user_id, request.cost)
            decisions.append(decision)

        # Check team policy
        if request.team_id and "team" in self._policies:
            decision = self._check_scope("team", request.team_id, request.cost)
            decisions.append(decision)

        # Check global policy
        if "global" in self._policies:
            decision = self._check_scope("global", "default", request.cost)
            decisions.append(decision)

        # Check per-request limit
        if request.user_id and "user" in self._policies:
            user_policy = self._policies["user"]
            max_per_request = user_policy.get("max_cost_per_request")
            if max_per_request and request.cost > max_per_request:
                decisions.append(PolicyDecision(
                    allowed=False,
                    action="block",
                    scope="user",
                    scope_id=request.user_id,
                    reason=f"Request cost ${request.cost:.4f} exceeds per-request limit ${max_per_request:.2f}",
                    budget_used=request.cost,
                    budget_limit=max_per_request,
                    utilization_percent=request.cost / max_per_request * 100,
                ))

        # Determine final action (most restrictive)
        final_action = "allow"
        would_block = False
        would_downgrade = False

        for d in decisions:
            if not d.allowed:
                if d.action == "block":
                    final_action = "block"
                    would_block = True
                elif d.action == "downgrade" and not would_block:
                    final_action = "downgrade"
                    would_downgrade = True
                elif d.action == "alert" and final_action == "allow":
                    final_action = "alert"

        return SimulationResult(
            request_index=index,
            request=request,
            decisions=decisions,
            final_action=final_action,
            would_be_blocked=would_block,
            would_be_downgraded=would_downgrade,
        )

    def _check_scope(self, scope: str, scope_id: str, cost: float) -> PolicyDecision:
        """Check a single scope's policy."""
        policy = self._policies.get(scope, {})
        limit_daily = policy.get("limit_daily", float("inf"))
        on_exceed = policy.get("on_exceed", "allow")

        # Get cumulative spend
        current = self._cumulative.get(scope, {}).get(scope_id, 0.0)
        projected = current + cost
        utilization = projected / limit_daily * 100 if limit_daily > 0 else 0.0

        if projected > limit_daily:
            return PolicyDecision(
                allowed=False,
                action=on_exceed,
                scope=scope,
                scope_id=scope_id,
                reason=f"{scope}:{scope_id} would exceed daily limit (${projected:.2f}/${limit_daily:.2f})",
                budget_used=projected,
                budget_limit=limit_daily,
                utilization_percent=utilization,
            )

        return PolicyDecision(
            allowed=True,
            action="allow",
            scope=scope,
            scope_id=scope_id,
            reason="Within budget",
            budget_used=projected,
            budget_limit=limit_daily,
            utilization_percent=utilization,
        )

    def _accumulate(self, request: SimulationRequest) -> None:
        """Track cumulative costs."""
        scopes = [("global", "default")]
        if request.team_id:
            scopes.append(("team", request.team_id))
        if request.user_id:
            scopes.append(("user", request.user_id))

        for scope, scope_id in scopes:
            if scope not in self._cumulative:
                self._cumulative[scope] = {}
            current = self._cumulative[scope].get(scope_id, 0.0)
            self._cumulative[scope][scope_id] = current + request.cost

    def _compute_utilization(self) -> Dict[str, Dict[str, float]]:
        """Compute budget utilization for all scopes."""
        utilization: Dict[str, Dict[str, float]] = {}

        for scope, scope_data in self._cumulative.items():
            policy = self._policies.get(scope, {})
            limit = policy.get("limit_daily", float("inf"))
            utilization[scope] = {}

            for scope_id, spent in scope_data.items():
                util_pct = spent / limit * 100 if limit > 0 else 0.0
                utilization[scope][scope_id] = util_pct

        return utilization

    def _generate_recommendations(
        self,
        blocked: int,
        downgraded: int,
        total_cost: float,
        total_requests: int,
        utilization: Dict[str, Dict[str, float]],
    ) -> List[str]:
        """Generate recommendations based on simulation results."""
        recs: List[str] = []

        if blocked == 0 and downgraded == 0:
            recs.append("All requests would pass current policies. Budget headroom is adequate.")
        else:
            block_rate = blocked / total_requests * 100 if total_requests > 0 else 0
            if block_rate > 20:
                recs.append(
                    f"High block rate ({block_rate:.0f}%). "
                    f"Consider increasing budget limits or switching to 'downgrade' action."
                )
            elif block_rate > 5:
                recs.append(
                    f"Moderate block rate ({block_rate:.0f}%). "
                    f"Review if limits are appropriate for current usage patterns."
                )

        # Check for hot scopes
        for scope, scope_data in utilization.items():
            for scope_id, util_pct in scope_data.items():
                if util_pct > 90:
                    recs.append(
                        f"{scope}:{scope_id} at {util_pct:.0f}% utilization — "
                        f"approaching limit. Consider increasing budget."
                    )

        return recs


def load_simulation_data(data_path: str) -> List[SimulationRequest]:
    """Load simulation data from a JSON file.

    Args:
        data_path: Path to JSON file with request data.

    Returns:
        List of SimulationRequest objects.
    """
    path = Path(data_path)
    if not path.exists():
        return []

    with open(path) as f:
        data = json.load(f)

    requests = []
    entries = data if isinstance(data, list) else data.get("requests", [])

    for entry in entries:
        requests.append(SimulationRequest(
            model=entry.get("model", "unknown"),
            input_tokens=entry.get("input_tokens", 0),
            output_tokens=entry.get("output_tokens", 0),
            cost=entry.get("cost", 0.0),
            user_id=entry.get("user_id"),
            team_id=entry.get("team_id"),
            endpoint=entry.get("endpoint"),
            timestamp=entry.get("timestamp"),
        ))

    return requests


def format_simulation_report(report: SimulationReport) -> str:
    """Format a simulation report for CLI output."""
    lines: List[str] = []
    lines.append("")
    lines.append("  ╭─ Policy Simulation Results ─────────────────────────╮")
    lines.append(f"  │ Total requests simulated: {report.total_requests:<24}│")
    lines.append(f"  │ Total cost simulated:     ${report.total_cost_simulated:<22.4f}│")
    lines.append(f"  │ Pass rate:                {report.pass_rate:<24.1f}│")
    lines.append("  ├──────────────────────────────────────────────────────┤")
    lines.append(f"  │ ✅ Allowed:    {report.allowed_count:<37}│")
    lines.append(f"  │ 🔴 Blocked:    {report.blocked_count:<37}│")
    lines.append(f"  │ 🟡 Downgraded: {report.downgraded_count:<37}│")
    lines.append(f"  │ ⚠️  Alerted:    {report.alerted_count:<37}│")
    lines.append("  ╰──────────────────────────────────────────────────────╯")

    if report.scope_utilization:
        lines.append("")
        lines.append("  Budget Utilization:")
        for scope, scope_data in report.scope_utilization.items():
            for scope_id, util_pct in scope_data.items():
                bar_len = min(20, int(util_pct / 5))
                bar = "█" * bar_len + "░" * (20 - bar_len)
                lines.append(f"    {scope}:{scope_id:<12} {bar} {util_pct:.0f}%")

    if report.recommendations:
        lines.append("")
        lines.append("  Recommendations:")
        for rec in report.recommendations:
            lines.append(f"    → {rec}")

    lines.append("")
    return "\n".join(lines)


def policies_test_command(args: argparse.Namespace) -> int:
    """Execute the policies test --simulate command.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Exit code (0=all pass, 1=violations found).
    """
    # Load policies from config
    policies = None
    config_path = getattr(args, "config", None)
    if config_path:
        try:
            import yaml  # type: ignore
            with open(config_path) as f:
                config = yaml.safe_load(f)
            policies = config.get("policies")
        except (ImportError, IOError):
            pass

    # Load simulation data
    data_path = getattr(args, "data", None)
    if data_path:
        requests = load_simulation_data(data_path)
    else:
        # Generate synthetic data for testing
        requests = _generate_synthetic_requests()

    # Run simulation
    simulator = PolicySimulator(policies=policies)
    report = simulator.simulate(requests)

    # Output
    output_format = getattr(args, "format", "table")
    if output_format == "json":
        output = {
            "total_requests": report.total_requests,
            "blocked": report.blocked_count,
            "downgraded": report.downgraded_count,
            "alerted": report.alerted_count,
            "allowed": report.allowed_count,
            "pass_rate": report.pass_rate,
            "total_cost": report.total_cost_simulated,
            "recommendations": report.recommendations,
        }
        print(json.dumps(output, indent=2))
    else:
        print(format_simulation_report(report))

    return 1 if report.blocked_count > 0 else 0


def _generate_synthetic_requests(count: int = 50) -> List[SimulationRequest]:
    """Generate synthetic requests for simulation."""
    import random
    random.seed(42)

    models = ["claude-3-haiku", "claude-3.5-sonnet", "claude-3-opus"]
    users = ["user-1", "user-2", "user-3", "user-4"]
    teams = ["engineering", "marketing", "data-science"]

    requests = []
    for _ in range(count):
        model = random.choice(models)
        cost_map = {"claude-3-haiku": 0.002, "claude-3.5-sonnet": 0.015, "claude-3-opus": 0.075}
        base_cost = cost_map.get(model, 0.01)
        cost = base_cost * random.uniform(0.5, 2.0)

        requests.append(SimulationRequest(
            model=model,
            input_tokens=random.randint(100, 4000),
            output_tokens=random.randint(50, 2000),
            cost=cost,
            user_id=random.choice(users),
            team_id=random.choice(teams),
        ))

    return requests


def register_policies_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the policies subcommand."""
    parser = subparsers.add_parser(
        "policies",
        help="Policy management and testing",
    )
    sub = parser.add_subparsers(dest="policies_action")

    test_parser = sub.add_parser("test", help="Test policies")
    test_parser.add_argument(
        "--simulate", action="store_true", required=True,
        help="Run dry-run simulation against data",
    )
    test_parser.add_argument("--config", help="Path to costsentinel.yaml")
    test_parser.add_argument("--data", help="Path to historical data JSON")
    test_parser.add_argument(
        "--format", choices=["table", "json"], default="table",
        help="Output format",
    )
    test_parser.set_defaults(func=policies_test_command)
