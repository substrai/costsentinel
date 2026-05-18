"""Tests for cost reporting."""

from datetime import datetime, timezone

import pytest

from costsentinel.core.config import CostSentinelConfig, PolicyConfig
from costsentinel.core.state import CostState
from costsentinel.policies.attribution import AttributionStore, CostAttribution
from costsentinel.reporting.reporter import CostReporter


class TestCostReporter:
    """Test suite for CostReporter."""

    @pytest.fixture
    def config(self, tmp_path):
        return CostSentinelConfig(
            project_name="test",
            state_file=str(tmp_path / "state.json"),
            attribution_file=str(tmp_path / "attr.json"),
        )

    @pytest.fixture
    def state(self, config):
        return CostState(config.state_file)

    @pytest.fixture
    def attribution(self, config):
        return AttributionStore(config.attribution_file)

    @pytest.fixture
    def reporter(self, config, state, attribution):
        return CostReporter(config, state, attribution)

    def _add_sample_data(self, state, attribution):
        """Add sample data for reporting tests."""
        state.increment("global", "default", 5.0)
        state.increment("team", "team-alpha", 3.0)
        state.increment("team", "team-beta", 2.0)
        state.increment("user", "user-1", 2.5)
        state.increment("user", "user-2", 1.5)
        state.increment("user", "user-3", 1.0)

        records = [
            ("user-1", "team-alpha", "/api/chat", "claude-3-haiku", 0.01),
            ("user-1", "team-alpha", "/api/chat", "claude-3.5-sonnet", 0.05),
            ("user-2", "team-beta", "/api/summarize", "claude-3-haiku", 0.008),
            ("user-3", "team-alpha", "/api/chat", "claude-3-haiku", 0.003),
        ]

        for user, team, ep, model, cost in records:
            attr = CostAttribution(
                user_id=user,
                team_id=team,
                endpoint=ep,
                model=model,
                timestamp=datetime.now(timezone.utc).isoformat(),
                cost=cost,
                tokens_in=1000,
                tokens_out=500,
            )
            attribution.record(attr)

    def test_daily_report_structure(self, reporter, state, attribution):
        self._add_sample_data(state, attribution)
        report = reporter.daily_report()

        assert "date" in report
        assert "global" in report
        assert "teams" in report
        assert "endpoints" in report
        assert "users" in report
        assert "summary" in report

    def test_daily_report_empty(self, reporter):
        report = reporter.daily_report()
        assert report["summary"]["total_calls"] == 0

    def test_breakdown_by_model(self, reporter, state, attribution):
        self._add_sample_data(state, attribution)
        breakdown = reporter.breakdown_by_model("daily")

        assert "claude-3-haiku" in breakdown
        assert "claude-3.5-sonnet" in breakdown
        assert breakdown["claude-3-haiku"]["calls"] == 3
        assert breakdown["claude-3.5-sonnet"]["calls"] == 1

    def test_breakdown_by_team(self, reporter, state, attribution):
        self._add_sample_data(state, attribution)
        breakdown = reporter.breakdown_by_team("daily")

        assert "team-alpha" in breakdown
        assert "team-beta" in breakdown

    def test_breakdown_by_endpoint(self, reporter, state, attribution):
        self._add_sample_data(state, attribution)
        breakdown = reporter.breakdown_by_endpoint("daily")

        assert "/api/chat" in breakdown
        assert "/api/summarize" in breakdown

    def test_top_users(self, reporter, state, attribution):
        self._add_sample_data(state, attribution)
        top = reporter.top_users(n=2, period="daily")

        assert len(top) == 2
        # First user should have highest cost
        assert top[0]["cost"] >= top[1]["cost"]

    def test_top_users_limit(self, reporter, state, attribution):
        self._add_sample_data(state, attribution)
        top = reporter.top_users(n=1, period="daily")
        assert len(top) == 1

    def test_format_report_text(self, reporter, state, attribution):
        self._add_sample_data(state, attribution)
        report = reporter.daily_report()
        text = reporter.format_report(report, format="text")

        assert "CostSentinel Daily Report" in text
        assert "Total Cost" in text
        assert "Total Calls" in text

    def test_format_report_json(self, reporter, state, attribution):
        self._add_sample_data(state, attribution)
        report = reporter.daily_report()
        text = reporter.format_report(report, format="json")

        import json
        parsed = json.loads(text)
        assert "date" in parsed
        assert "summary" in parsed

    def test_format_report_default(self, reporter):
        # Should generate daily report if no data passed
        text = reporter.format_report(format="text")
        assert "CostSentinel Daily Report" in text
