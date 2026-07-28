"""Tests for S3 export for cost attribution data."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from costsentinel.reporting.s3_export import (
    AttributionRecord,
    ExportResult,
    S3CostExporter,
)


def _make_records(count: int = 5) -> list:
    return [
        AttributionRecord(
            timestamp="2026-06-27T12:00:00Z",
            model="claude-3-haiku",
            cost_usd=0.0024,
            input_tokens=500,
            output_tokens=200,
            user_id=f"user-{i}",
            team_id="engineering",
            endpoint="/api/chat",
        )
        for i in range(count)
    ]


class TestAttributionRecord:
    def test_to_dict_includes_all_fields(self):
        record = AttributionRecord(
            timestamp="2026-06-27T00:00:00Z",
            model="haiku",
            cost_usd=0.002,
            input_tokens=400,
            output_tokens=150,
            user_id="u1",
            team_id="eng",
            endpoint="/api",
        )
        d = record.to_dict()
        assert d["model"] == "haiku"
        assert d["cost_usd"] == 0.002
        assert d["total_tokens"] == 550
        assert "cost_per_token" in d

    def test_total_tokens_computed(self):
        record = AttributionRecord(
            timestamp="t", model="m", cost_usd=0.1,
            input_tokens=300, output_tokens=200,
        )
        assert record.to_dict()["total_tokens"] == 500

    def test_cost_per_token_calculated(self):
        record = AttributionRecord(
            timestamp="t", model="m", cost_usd=0.001,
            input_tokens=400, output_tokens=100,
        )
        d = record.to_dict()
        expected = 0.001 / 500
        assert abs(d["cost_per_token"] - expected) < 1e-9

    def test_zero_tokens_no_division_error(self):
        record = AttributionRecord(
            timestamp="t", model="m", cost_usd=0.0,
            input_tokens=0, output_tokens=0,
        )
        d = record.to_dict()
        assert d["cost_per_token"] == 0.0


class TestS3ExporterInit:
    def test_default_config(self):
        e = S3CostExporter()
        assert e.bucket == "substrai-cost-data"
        assert e.prefix == "costs"

    def test_custom_config(self):
        e = S3CostExporter(bucket="my-bucket", prefix="data/costs")
        assert e.bucket == "my-bucket"
        assert e.prefix == "data/costs"


class TestLocalExport:
    def test_export_jsonl_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            e = S3CostExporter(bucket="test", local_fallback_dir=tmp)
            records = _make_records(3)
            result = e.export(records, format="jsonl")

            assert result.success is True
            assert result.record_count == 3
            assert result.format == "jsonl"

            # Verify file written
            written = Path(result.key.replace("costs/", tmp + "/costs/", 1))
            if not written.exists():
                # Try direct path
                written = Path(tmp) / result.key
            assert written.exists()

    def test_export_json_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            e = S3CostExporter(bucket="test", local_fallback_dir=tmp)
            records = _make_records(2)
            result = e.export(records, format="json")
            assert result.format == "json"

    def test_file_is_valid_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            e = S3CostExporter(bucket="b", prefix="p", local_fallback_dir=tmp)
            records = _make_records(3)
            result = e.export(records, format="jsonl")

            file_path = Path(tmp) / result.key
            lines = file_path.read_text().strip().split("\n")
            assert len(lines) == 3
            for line in lines:
                obj = json.loads(line)
                assert "model" in obj
                assert "cost_usd" in obj

    def test_partition_by_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            e = S3CostExporter(bucket="b", local_fallback_dir=tmp)
            dt = datetime(2026, 6, 27, tzinfo=timezone.utc)
            result = e.export(_make_records(1), partition_date=dt)
            assert "year=2026" in result.partition
            assert "month=06" in result.partition
            assert "day=27" in result.partition

    def test_s3_uri_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            e = S3CostExporter(bucket="my-bucket", local_fallback_dir=tmp)
            result = e.export(_make_records(1))
            assert result.s3_uri.startswith("s3://my-bucket/")

    def test_file_size_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            e = S3CostExporter(bucket="b", local_fallback_dir=tmp)
            result = e.export(_make_records(5))
            assert result.file_size_bytes > 0

    def test_export_time_tracked(self):
        with tempfile.TemporaryDirectory() as tmp:
            e = S3CostExporter(bucket="b", local_fallback_dir=tmp)
            result = e.export(_make_records(5))
            assert result.export_time_ms >= 0


class TestDailySummaryExport:
    def test_summary_aggregates_by_team_model_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            e = S3CostExporter(bucket="b", local_fallback_dir=tmp)

            records = [
                AttributionRecord("t", "haiku", 0.001, 200, 100, team_id="eng", endpoint="/chat"),
                AttributionRecord("t", "haiku", 0.002, 300, 150, team_id="eng", endpoint="/chat"),
                AttributionRecord("t", "sonnet", 0.01, 500, 200, team_id="data", endpoint="/api"),
            ]
            result = e.export_daily_summary(records)
            assert result.success is True
            assert result.record_count == 2  # Two unique (team, model, endpoint) groups

    def test_summary_key_contains_daily(self):
        with tempfile.TemporaryDirectory() as tmp:
            e = S3CostExporter(bucket="b", local_fallback_dir=tmp)
            result = e.export_daily_summary(_make_records(3))
            assert "daily_summary" in result.key


class TestAthenaDDL:
    def test_ddl_contains_table_name(self):
        e = S3CostExporter(bucket="my-bucket", prefix="data")
        ddl = e.generate_athena_ddl()
        assert "CREATE EXTERNAL TABLE" in ddl
        assert "substrai_costs" in ddl

    def test_ddl_contains_bucket(self):
        e = S3CostExporter(bucket="my-bucket")
        ddl = e.generate_athena_ddl()
        assert "my-bucket" in ddl

    def test_ddl_has_partitions(self):
        e = S3CostExporter()
        ddl = e.generate_athena_ddl()
        assert "PARTITIONED BY" in ddl
        assert "year" in ddl
        assert "month" in ddl
        assert "day" in ddl

    def test_ddl_is_valid_sql_structure(self):
        e = S3CostExporter()
        ddl = e.generate_athena_ddl()
        assert ddl.strip().startswith("CREATE")
        assert "cost_usd DOUBLE" in ddl
        assert "model STRING" in ddl
