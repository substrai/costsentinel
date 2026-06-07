"""Tests for report CLI command."""

import pytest

from costsentinel.core.config import CostSentinelConfig, PolicyConfig
from costsentinel.core.state import CostState
from costsentinel.cli.report import ReportFilter, generate_report, CostReport


@pytest.fixture
def state(tmp_path):
    """Create a state with test data."""
    s = CostState(str(tmp_path / "state.json"))
    s.increment("global", "default", 5.0)
    s.increment("team", "alpha", 3.0)
    s.increment("team", "beta", 2.0)
    s.increment("endpoint", "api-v1", 1.5)
    s.increment("user", "user-1", 0.8)
    return s


@pytest.fixture
def config():
    return CostSentinelConfig(
        policies=[PolicyConfig(scope="global", limit_daily=100.0)],
    )


def test_report_filter_defaults():
    f = ReportFilter()
    assert f.period == "7d"
    assert f.team is None


def test_report_filter_start_time():
    f = ReportFilter(period="7d")
    start = f.start_time
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    diff = (now - start).days
    assert diff == 7 or diff == 6  # allow for timing


def test_report_filter_hours():
    f = ReportFilter(period="24h")
    start = f.start_time
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    diff = (now - start).total_seconds()
    assert abs(diff - 86400) < 5


def test_generate_report_all_scopes(state):
    report = generate_report(state)
    assert isinstance(report, CostReport)
    assert report.total_cost > 0
    assert len(report.entries) > 0


def test_generate_report_team_filter(state):
    f = ReportFilter(team="alpha")
    report = generate_report(state, report_filter=f)
    assert len(report.entries) == 1
    assert report.entries[0].scope_id == "alpha"
    assert report.entries[0].daily_cost == 3.0


def test_generate_report_user_filter(state):
    f = ReportFilter(user="user-1")
    report = generate_report(state, report_filter=f)
    assert len(report.entries) == 1
    assert report.entries[0].daily_cost == 0.8


def test_report_to_dict(state):
    report = generate_report(state)
    d = report.to_dict()
    assert "title" in d
    assert "summary" in d
    assert "entries" in d
    assert d["summary"]["total_cost"] > 0


def test_report_to_text(state):
    report = generate_report(state)
    text = report.to_text()
    assert "CostSentinel Report" in text
    assert "Total Cost" in text


def test_report_with_config_budget_utilization(state, config):
    report = generate_report(state, config=config)
    global_entries = [e for e in report.entries if e.scope == "global"]
    if global_entries:
        assert global_entries[0].budget_utilization > 0


def test_report_sorted_by_cost(state):
    report = generate_report(state)
    costs = [e.daily_cost for e in report.entries]
    assert costs == sorted(costs, reverse=True)
