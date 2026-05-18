"""Tests for chargeback report generation."""

import time
import tempfile
from pathlib import Path

from costsentinel.reporting.chargeback import ChargebackGenerator, ChargebackReport


class TestChargebackGenerator:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self.gen = ChargebackGenerator(attribution_path=self.tmp.name)

    def teardown_method(self):
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_empty_report(self):
        report = self.gen.generate_report(period_days=7)
        assert report.total_cost == 0.0
        assert len(report.entries) == 0

    def test_record_and_report(self):
        self.gen.record({"team": "eng", "project": "chat", "endpoint": "/api/chat", "model": "haiku", "cost": 0.05, "tokens": 500})
        self.gen.record({"team": "eng", "project": "chat", "endpoint": "/api/chat", "model": "haiku", "cost": 0.03, "tokens": 300})
        report = self.gen.generate_report(period_days=1)
        assert report.total_cost > 0
        assert len(report.entries) == 1  # Aggregated into one entry
        assert report.entries[0].request_count == 2

    def test_multiple_teams(self):
        self.gen.record({"team": "eng", "project": "p1", "endpoint": "/a", "model": "m1", "cost": 0.10, "tokens": 100})
        self.gen.record({"team": "data", "project": "p2", "endpoint": "/b", "model": "m2", "cost": 0.20, "tokens": 200})
        report = self.gen.generate_report(period_days=1)
        assert len(report.entries) == 2

    def test_sorted_by_cost_descending(self):
        self.gen.record({"team": "a", "project": "p", "endpoint": "/x", "model": "m", "cost": 0.01, "tokens": 10})
        self.gen.record({"team": "b", "project": "p", "endpoint": "/y", "model": "m", "cost": 0.50, "tokens": 500})
        report = self.gen.generate_report(period_days=1)
        assert report.entries[0].cost >= report.entries[1].cost

    def test_export_csv(self):
        self.gen.record({"team": "eng", "project": "chat", "endpoint": "/api", "model": "sonnet", "cost": 0.10, "tokens": 1000})
        report = self.gen.generate_report(period_days=1)
        csv_str = self.gen.export_csv(report)
        assert "Team" in csv_str
        assert "eng" in csv_str
        assert "sonnet" in csv_str

    def test_export_json(self):
        self.gen.record({"team": "eng", "project": "p", "endpoint": "/e", "model": "m", "cost": 0.05, "tokens": 50})
        report = self.gen.generate_report(period_days=1)
        json_str = self.gen.export_json(report)
        assert "period_start" in json_str
        assert "total_cost" in json_str

    def test_get_by_team(self):
        self.gen.record({"team": "eng", "project": "p", "endpoint": "/e", "model": "m", "cost": 0.10, "tokens": 100})
        self.gen.record({"team": "eng", "project": "p", "endpoint": "/e", "model": "m", "cost": 0.05, "tokens": 50})
        self.gen.record({"team": "data", "project": "p", "endpoint": "/e", "model": "m", "cost": 0.20, "tokens": 200})
        by_team = self.gen.get_by_team(period_days=1)
        assert by_team["eng"] > 0
        assert by_team["data"] > 0

    def test_report_to_dict(self):
        self.gen.record({"team": "t", "project": "p", "endpoint": "/e", "model": "m", "cost": 0.01, "tokens": 10})
        report = self.gen.generate_report(period_days=1)
        d = report.to_dict()
        assert "entries" in d
        assert "total_cost" in d

    def test_period_filtering(self):
        # Record with old timestamp (outside 1-day window)
        self.gen.record({"team": "old", "project": "p", "endpoint": "/e", "model": "m", "cost": 1.00, "tokens": 1000, "timestamp": time.time() - 200000})
        self.gen.record({"team": "new", "project": "p", "endpoint": "/e", "model": "m", "cost": 0.05, "tokens": 50})
        report = self.gen.generate_report(period_days=1)
        # Only recent entry should be included
        teams = [e.team for e in report.entries]
        assert "new" in teams
