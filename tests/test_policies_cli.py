"""Tests for 'costsentinel policies test --simulate' CLI command."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from costsentinel.cli.policies import (
    PolicySimulator,
    SimulationReport,
    SimulationRequest,
    format_simulation_report,
    load_simulation_data,
)


def _make_requests(count: int = 10, cost: float = 1.0) -> list:
    """Create test requests."""
    return [
        SimulationRequest(
            model="claude-3-haiku",
            input_tokens=500,
            output_tokens=200,
            cost=cost,
            user_id="user-1",
            team_id="engineering",
        )
        for _ in range(count)
    ]


class TestPolicySimulator:
    """Test the policy simulator."""

    def test_all_requests_pass(self):
        simulator = PolicySimulator(policies={
            "global": {"limit_daily": 1000.0, "on_exceed": "block"},
        })
        requests = _make_requests(count=5, cost=0.01)
        report = simulator.simulate(requests)
        assert report.blocked_count == 0
        assert report.allowed_count == 5
        assert report.pass_rate == 100.0

    def test_requests_blocked_by_global_limit(self):
        simulator = PolicySimulator(policies={
            "global": {"limit_daily": 5.0, "on_exceed": "block"},
        })
        requests = _make_requests(count=10, cost=1.0)
        report = simulator.simulate(requests)
        # After 5 requests ($5 total), subsequent should be blocked
        assert report.blocked_count > 0
        assert report.allowed_count < 10

    def test_requests_downgraded_by_team_limit(self):
        simulator = PolicySimulator(policies={
            "global": {"limit_daily": 1000.0, "on_exceed": "block"},
            "team": {"limit_daily": 3.0, "on_exceed": "downgrade"},
        })
        requests = _make_requests(count=10, cost=1.0)
        report = simulator.simulate(requests)
        assert report.downgraded_count > 0

    def test_per_request_limit(self):
        simulator = PolicySimulator(policies={
            "user": {"limit_daily": 100.0, "on_exceed": "block", "max_cost_per_request": 0.50},
        })
        requests = [
            SimulationRequest(
                model="claude-3-opus", input_tokens=5000,
                output_tokens=2000, cost=0.75,
                user_id="user-1", team_id="eng",
            ),
        ]
        report = simulator.simulate(requests)
        assert report.blocked_count == 1

    def test_multiple_users_independent_budgets(self):
        simulator = PolicySimulator(policies={
            "user": {"limit_daily": 3.0, "on_exceed": "block"},
        })
        requests = [
            SimulationRequest(model="m", input_tokens=100, output_tokens=50,
                              cost=2.0, user_id="user-a", team_id="t"),
            SimulationRequest(model="m", input_tokens=100, output_tokens=50,
                              cost=2.0, user_id="user-b", team_id="t"),
            SimulationRequest(model="m", input_tokens=100, output_tokens=50,
                              cost=2.0, user_id="user-a", team_id="t"),  # Should be blocked
        ]
        report = simulator.simulate(requests)
        assert report.blocked_count == 1  # Only user-a's second request blocked
        assert report.allowed_count == 2

    def test_total_cost_tracked(self):
        simulator = PolicySimulator(policies={
            "global": {"limit_daily": 1000.0, "on_exceed": "block"},
        })
        requests = _make_requests(count=5, cost=2.0)
        report = simulator.simulate(requests)
        assert abs(report.total_cost_simulated - 10.0) < 0.01

    def test_utilization_calculated(self):
        simulator = PolicySimulator(policies={
            "global": {"limit_daily": 100.0, "on_exceed": "block"},
        })
        requests = _make_requests(count=5, cost=10.0)
        report = simulator.simulate(requests)
        assert "global" in report.scope_utilization
        assert report.scope_utilization["global"]["default"] == 50.0


class TestSimulationReport:
    """Test report properties."""

    def test_block_rate(self):
        report = SimulationReport(
            total_requests=100,
            blocked_count=20,
            downgraded_count=5,
            alerted_count=3,
            allowed_count=72,
            total_cost_simulated=50.0,
            policy_violations=[],
            scope_utilization={},
            recommendations=[],
        )
        assert report.block_rate == 20.0
        assert report.pass_rate == 72.0

    def test_zero_requests(self):
        report = SimulationReport(
            total_requests=0,
            blocked_count=0,
            downgraded_count=0,
            alerted_count=0,
            allowed_count=0,
            total_cost_simulated=0.0,
            policy_violations=[],
            scope_utilization={},
            recommendations=[],
        )
        assert report.block_rate == 0.0
        assert report.pass_rate == 100.0


class TestLoadSimulationData:
    """Test loading data from JSON files."""

    def test_load_array_format(self):
        data = [
            {"model": "claude-3-haiku", "input_tokens": 500, "output_tokens": 200,
             "cost": 0.002, "user_id": "u1", "team_id": "eng"},
            {"model": "claude-3-sonnet", "input_tokens": 1000, "output_tokens": 500,
             "cost": 0.015, "user_id": "u2", "team_id": "data"},
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name

        requests = load_simulation_data(path)
        assert len(requests) == 2
        assert requests[0].model == "claude-3-haiku"
        assert requests[1].cost == 0.015

    def test_load_wrapped_format(self):
        data = {"requests": [
            {"model": "m1", "input_tokens": 100, "output_tokens": 50, "cost": 0.01}
        ]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name

        requests = load_simulation_data(path)
        assert len(requests) == 1

    def test_load_nonexistent_file(self):
        requests = load_simulation_data("/nonexistent/data.json")
        assert requests == []


class TestFormatReport:
    """Test report formatting."""

    def test_format_includes_counts(self):
        report = SimulationReport(
            total_requests=50,
            blocked_count=5,
            downgraded_count=3,
            alerted_count=2,
            allowed_count=40,
            total_cost_simulated=25.5,
            policy_violations=[],
            scope_utilization={"global": {"default": 75.0}},
            recommendations=["Increase budget limits."],
        )
        output = format_simulation_report(report)
        assert "50" in output
        assert "Allowed" in output
        assert "Blocked" in output
        assert "Recommendations" in output

    def test_format_includes_utilization_bar(self):
        report = SimulationReport(
            total_requests=10,
            blocked_count=0,
            downgraded_count=0,
            alerted_count=0,
            allowed_count=10,
            total_cost_simulated=5.0,
            policy_violations=[],
            scope_utilization={"global": {"default": 50.0}},
            recommendations=[],
        )
        output = format_simulation_report(report)
        assert "█" in output or "░" in output


class TestRecommendations:
    """Test recommendation generation."""

    def test_no_violations_recommendation(self):
        simulator = PolicySimulator(policies={
            "global": {"limit_daily": 1000.0, "on_exceed": "block"},
        })
        requests = _make_requests(count=3, cost=0.01)
        report = simulator.simulate(requests)
        assert any("pass" in r.lower() or "adequate" in r.lower() for r in report.recommendations)

    def test_high_block_rate_recommendation(self):
        simulator = PolicySimulator(policies={
            "global": {"limit_daily": 2.0, "on_exceed": "block"},
        })
        requests = _make_requests(count=20, cost=1.0)
        report = simulator.simulate(requests)
        assert any("block rate" in r.lower() or "increase" in r.lower() for r in report.recommendations)
