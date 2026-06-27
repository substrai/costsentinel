"""Tests for the 'costsentinel anomalies' CLI command."""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path

import pytest

from costsentinel.cli.anomalies import (
    AnomalyRecord,
    anomalies_command,
    filter_anomalies,
    format_anomaly_table,
    load_anomalies,
    parse_time_range,
    register_anomalies_parser,
)


class TestParseTimeRange:
    """Test time range parsing."""

    def test_parse_hours(self):
        assert parse_time_range("1h") == 3600
        assert parse_time_range("24h") == 86400
        assert parse_time_range("2h") == 7200

    def test_parse_days(self):
        assert parse_time_range("1d") == 86400
        assert parse_time_range("7d") == 604800
        assert parse_time_range("30d") == 2592000

    def test_parse_weeks(self):
        assert parse_time_range("1w") == 604800
        assert parse_time_range("2w") == 1209600

    def test_parse_with_whitespace(self):
        assert parse_time_range("  24h  ") == 86400

    def test_parse_case_insensitive(self):
        assert parse_time_range("24H") == 86400
        assert parse_time_range("7D") == 604800

    def test_invalid_format(self):
        with pytest.raises(ValueError):
            parse_time_range("abc")

    def test_invalid_number(self):
        with pytest.raises(ValueError):
            parse_time_range("xxh")

    def test_missing_unit(self):
        with pytest.raises(ValueError):
            parse_time_range("24")


class TestLoadAnomalies:
    """Test loading anomaly records from file."""

    def test_load_from_valid_file(self):
        records = [
            {
                "timestamp": time.time(),
                "severity": "critical",
                "scope": "team",
                "scope_id": "engineering",
                "message": "Cost spike detected",
                "current_value": 50.0,
                "baseline_value": 10.0,
                "deviation_factor": 5.0,
                "recommended_action": "Review recent deployments",
            }
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(records, f)
            path = f.name

        loaded = load_anomalies(path)
        assert len(loaded) == 1
        assert loaded[0].severity == "critical"
        assert loaded[0].scope_id == "engineering"

    def test_load_from_nonexistent_file(self):
        result = load_anomalies("/nonexistent/path.json")
        assert result == []

    def test_load_from_invalid_json(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json{{{")
            path = f.name

        result = load_anomalies(path)
        assert result == []

    def test_load_wrapped_format(self):
        data = {
            "anomalies": [
                {
                    "timestamp": time.time(),
                    "severity": "warning",
                    "scope": "global",
                    "scope_id": "default",
                    "message": "Elevated spending",
                    "current_value": 20.0,
                    "baseline_value": 12.0,
                    "deviation_factor": 1.7,
                }
            ]
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name

        loaded = load_anomalies(path)
        assert len(loaded) == 1
        assert loaded[0].severity == "warning"


class TestFilterAnomalies:
    """Test anomaly filtering."""

    def _make_records(self):
        now = time.time()
        return [
            AnomalyRecord(
                timestamp=now - 3600,  # 1 hour ago
                severity="critical",
                scope="team",
                scope_id="engineering",
                message="Cost spike",
                current_value=50.0,
                baseline_value=10.0,
                deviation_factor=5.0,
                recommended_action="Investigate",
            ),
            AnomalyRecord(
                timestamp=now - 7200,  # 2 hours ago
                severity="warning",
                scope="user",
                scope_id="user-1",
                message="Elevated usage",
                current_value=8.0,
                baseline_value=5.0,
                deviation_factor=1.6,
                recommended_action="Monitor",
            ),
            AnomalyRecord(
                timestamp=now - 172800,  # 2 days ago
                severity="critical",
                scope="global",
                scope_id="default",
                message="Budget exceeded",
                current_value=100.0,
                baseline_value=20.0,
                deviation_factor=5.0,
                recommended_action="Block requests",
            ),
        ]

    def test_filter_by_time_range_24h(self):
        records = self._make_records()
        filtered = filter_anomalies(records, time_range_seconds=86400)
        assert len(filtered) == 2  # Only the recent two

    def test_filter_by_time_range_1h(self):
        records = self._make_records()
        filtered = filter_anomalies(records, time_range_seconds=3600)
        # Only the one from exactly 1h ago (borderline)
        assert len(filtered) <= 1

    def test_filter_by_severity_critical(self):
        records = self._make_records()
        filtered = filter_anomalies(records, time_range_seconds=604800, severity="critical")
        assert all(r.severity == "critical" for r in filtered)
        assert len(filtered) == 2

    def test_filter_by_scope_team(self):
        records = self._make_records()
        filtered = filter_anomalies(records, time_range_seconds=604800, scope="team")
        assert len(filtered) == 1
        assert filtered[0].scope_id == "engineering"

    def test_filter_by_scope_id(self):
        records = self._make_records()
        filtered = filter_anomalies(records, time_range_seconds=604800, scope_id="user-1")
        assert len(filtered) == 1

    def test_results_sorted_most_recent_first(self):
        records = self._make_records()
        filtered = filter_anomalies(records, time_range_seconds=604800)
        timestamps = [r.timestamp for r in filtered]
        assert timestamps == sorted(timestamps, reverse=True)


class TestFormatAnomalyTable:
    """Test table formatting."""

    def test_empty_records(self):
        output = format_anomaly_table([])
        assert "No anomalies detected" in output

    def test_formats_records(self):
        records = [
            AnomalyRecord(
                timestamp=time.time() - 100,
                severity="critical",
                scope="team",
                scope_id="eng",
                message="Cost spike on claude-3-opus",
                current_value=50.0,
                baseline_value=10.0,
                deviation_factor=5.0,
                recommended_action="Switch to haiku",
            ),
        ]
        output = format_anomaly_table(records)
        assert "critical" in output
        assert "team:eng" in output
        assert "5.0x" in output
        assert "Total: 1" in output

    def test_shows_recommendations_for_critical(self):
        records = [
            AnomalyRecord(
                timestamp=time.time(),
                severity="critical",
                scope="global",
                scope_id="default",
                message="Budget exceeded",
                current_value=100.0,
                baseline_value=20.0,
                deviation_factor=5.0,
                recommended_action="Reduce traffic immediately",
            ),
        ]
        output = format_anomaly_table(records)
        assert "Recommended Actions" in output
        assert "Reduce traffic immediately" in output

    def test_shows_severity_counts(self):
        records = [
            AnomalyRecord(
                timestamp=time.time(), severity="critical", scope="global",
                scope_id="d", message="m", current_value=1, baseline_value=1,
                deviation_factor=1, recommended_action="a",
            ),
            AnomalyRecord(
                timestamp=time.time(), severity="warning", scope="global",
                scope_id="d", message="m", current_value=1, baseline_value=1,
                deviation_factor=1, recommended_action="a",
            ),
        ]
        output = format_anomaly_table(records)
        assert "Critical: 1" in output
        assert "Warning: 1" in output


class TestAnomaliesCommand:
    """Test the CLI command execution."""

    def test_command_with_no_anomalies(self, capsys):
        args = argparse.Namespace(
            last="24h",
            severity=None,
            scope=None,
            id=None,
            format="table",
            file="/nonexistent/anomalies.json",
        )
        exit_code = anomalies_command(args)
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "No anomalies detected" in captured.out

    def test_command_with_critical_returns_1(self):
        records = [
            {
                "timestamp": time.time(),
                "severity": "critical",
                "scope": "global",
                "scope_id": "default",
                "message": "Alert",
                "current_value": 50.0,
                "baseline_value": 10.0,
                "deviation_factor": 5.0,
                "recommended_action": "Act now",
            }
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(records, f)
            path = f.name

        args = argparse.Namespace(
            last="24h", severity=None, scope=None, id=None,
            format="table", file=path,
        )
        exit_code = anomalies_command(args)
        assert exit_code == 1

    def test_command_json_output(self, capsys):
        records = [
            {
                "timestamp": time.time(),
                "severity": "warning",
                "scope": "team",
                "scope_id": "data",
                "message": "Spike",
                "current_value": 15.0,
                "baseline_value": 10.0,
                "deviation_factor": 1.5,
            }
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(records, f)
            path = f.name

        args = argparse.Namespace(
            last="24h", severity=None, scope=None, id=None,
            format="json", file=path,
        )
        exit_code = anomalies_command(args)
        assert exit_code == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert isinstance(output, list)

    def test_command_invalid_time_range(self, capsys):
        args = argparse.Namespace(
            last="invalid", severity=None, scope=None, id=None,
            format="table", file="x.json",
        )
        exit_code = anomalies_command(args)
        assert exit_code == 2


class TestRegisterParser:
    """Test parser registration."""

    def test_register_adds_subcommand(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        register_anomalies_parser(subparsers)
        args = parser.parse_args(["anomalies", "--last", "24h"])
        assert args.last == "24h"
