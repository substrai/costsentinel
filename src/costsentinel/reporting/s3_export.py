"""S3 export for cost attribution data (Parquet-compatible format).

Exports cost attribution records to S3 for Athena/QuickSight analysis.
Writes columnar JSON (JSON Lines) that can be queried directly by
Athena, or converted to Parquet via AWS Glue.

Usage:
    from costsentinel.reporting.s3_export import S3CostExporter

    exporter = S3CostExporter(bucket="my-cost-data", prefix="substrai/costs")
    result = exporter.export(records=attribution_records)
    print(f"Exported to: {result.s3_uri}")
"""

from __future__ import annotations

import io
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class AttributionRecord:
    """A single cost attribution record for export."""

    timestamp: str
    model: str
    cost_usd: float
    input_tokens: int
    output_tokens: int
    user_id: str = "unknown"
    team_id: str = "unknown"
    endpoint: str = "unknown"
    scope: str = "global"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "model": self.model,
            "cost_usd": self.cost_usd,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
            "user_id": self.user_id,
            "team_id": self.team_id,
            "endpoint": self.endpoint,
            "scope": self.scope,
            "cost_per_token": round(
                self.cost_usd / (self.input_tokens + self.output_tokens), 8
            ) if (self.input_tokens + self.output_tokens) > 0 else 0.0,
            **self.metadata,
        }


@dataclass
class ExportResult:
    """Result of an S3 export operation."""

    s3_uri: str
    bucket: str
    key: str
    record_count: int
    file_size_bytes: int
    export_time_ms: float
    format: str  # "jsonl" or "json"
    partition: str  # e.g., "year=2026/month=06/day=27"
    success: bool
    error: Optional[str] = None


class S3CostExporter:
    """Exports cost attribution data to S3 for analytics.

    Writes records as JSON Lines (one JSON object per line) partitioned
    by date (Hive-style partitioning for Athena compatibility).

    Args:
        bucket: S3 bucket name.
        prefix: S3 key prefix (e.g., 'substrai/costs').
        region: AWS region for S3 (default: us-east-1).
        local_fallback_dir: Local directory for dev/test (no AWS needed).
    """

    def __init__(
        self,
        bucket: str = "substrai-cost-data",
        prefix: str = "costs",
        region: str = "us-east-1",
        local_fallback_dir: Optional[str] = None,
    ):
        self._bucket = bucket
        self._prefix = prefix
        self._region = region
        self._local_dir = local_fallback_dir

    @property
    def bucket(self) -> str:
        return self._bucket

    @property
    def prefix(self) -> str:
        return self._prefix

    def export(
        self,
        records: List[AttributionRecord],
        partition_date: Optional[datetime] = None,
        format: str = "jsonl",
    ) -> ExportResult:
        """Export attribution records to S3.

        Args:
            records: Cost attribution records to export.
            partition_date: Date for Hive partitioning (default: now).
            format: 'jsonl' (one record per line) or 'json' (array).

        Returns:
            ExportResult with S3 URI and stats.
        """
        start = time.time()
        dt = partition_date or datetime.now(tz=timezone.utc)
        partition = self._hive_partition(dt)

        # Build S3 key
        timestamp_str = dt.strftime("%Y%m%d_%H%M%S")
        key = f"{self._prefix}/{partition}/costs_{timestamp_str}.{format}"

        # Serialize records
        content = self._serialize(records, format)
        content_bytes = content.encode("utf-8")

        # Upload (try S3 first, fall back to local)
        success = True
        error = None
        if self._local_dir:
            self._write_local(key, content)
        else:
            success, error = self._upload_to_s3(key, content_bytes)

        elapsed = (time.time() - start) * 1000
        s3_uri = f"s3://{self._bucket}/{key}"

        return ExportResult(
            s3_uri=s3_uri,
            bucket=self._bucket,
            key=key,
            record_count=len(records),
            file_size_bytes=len(content_bytes),
            export_time_ms=elapsed,
            format=format,
            partition=partition,
            success=success,
            error=error,
        )

    def export_daily_summary(
        self,
        records: List[AttributionRecord],
        date: Optional[datetime] = None,
    ) -> ExportResult:
        """Export a daily aggregated summary to S3.

        Aggregates by team, model, and endpoint for cost dashboards.

        Args:
            records: Raw attribution records for the day.
            date: Date for the summary (default: today).

        Returns:
            ExportResult for the summary file.
        """
        dt = date or datetime.now(tz=timezone.utc)

        # Aggregate by (team_id, model, endpoint)
        summary: Dict[str, Dict[str, Any]] = {}
        for record in records:
            key = f"{record.team_id}::{record.model}::{record.endpoint}"
            if key not in summary:
                summary[key] = {
                    "date": dt.strftime("%Y-%m-%d"),
                    "team_id": record.team_id,
                    "model": record.model,
                    "endpoint": record.endpoint,
                    "total_cost_usd": 0.0,
                    "total_tokens": 0,
                    "call_count": 0,
                }
            summary[key]["total_cost_usd"] += record.cost_usd
            summary[key]["total_tokens"] += record.input_tokens + record.output_tokens
            summary[key]["call_count"] += 1

        # Round costs
        for v in summary.values():
            v["total_cost_usd"] = round(v["total_cost_usd"], 6)
            v["avg_cost_per_call"] = round(v["total_cost_usd"] / v["call_count"], 6)

        # Export as summary records
        summary_records = [
            AttributionRecord(
                timestamp=dt.isoformat(),
                model=v["model"],
                cost_usd=v["total_cost_usd"],
                input_tokens=v["total_tokens"] // 2,
                output_tokens=v["total_tokens"] // 2,
                team_id=v["team_id"],
                endpoint=v["endpoint"],
                metadata={"call_count": v["call_count"], "summary": True},
            )
            for v in summary.values()
        ]

        partition = self._hive_partition(dt)
        key = f"{self._prefix}/{partition}/daily_summary_{dt.strftime('%Y%m%d')}.jsonl"

        content = self._serialize(summary_records, "jsonl")
        content_bytes = content.encode("utf-8")

        start = time.time()
        if self._local_dir:
            self._write_local(key, content)
            success, error = True, None
        else:
            success, error = self._upload_to_s3(key, content_bytes)

        elapsed = (time.time() - start) * 1000

        return ExportResult(
            s3_uri=f"s3://{self._bucket}/{key}",
            bucket=self._bucket,
            key=key,
            record_count=len(summary_records),
            file_size_bytes=len(content_bytes),
            export_time_ms=elapsed,
            format="jsonl",
            partition=partition,
            success=success,
            error=error,
        )

    def generate_athena_ddl(self) -> str:
        """Generate CREATE TABLE DDL for Athena.

        Returns:
            SQL DDL string for creating an Athena table over the S3 data.
        """
        return f"""CREATE EXTERNAL TABLE IF NOT EXISTS substrai_costs (
    timestamp STRING,
    model STRING,
    cost_usd DOUBLE,
    input_tokens INT,
    output_tokens INT,
    total_tokens INT,
    user_id STRING,
    team_id STRING,
    endpoint STRING,
    scope STRING,
    cost_per_token DOUBLE
)
PARTITIONED BY (
    year STRING,
    month STRING,
    day STRING
)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
STORED AS TEXTFILE
LOCATION 's3://{self._bucket}/{self._prefix}/'
TBLPROPERTIES ('has_encrypted_data'='false');"""

    def _serialize(self, records: List[AttributionRecord], format: str) -> str:
        """Serialize records to JSON Lines or JSON array."""
        dicts = [r.to_dict() for r in records]
        if format == "json":
            return json.dumps(dicts, indent=2, default=str)
        # JSON Lines: one record per line
        return "\n".join(json.dumps(d, default=str) for d in dicts) + "\n"

    def _hive_partition(self, dt: datetime) -> str:
        """Build Hive-style partition path."""
        return f"year={dt.year}/month={dt.month:02d}/day={dt.day:02d}"

    def _upload_to_s3(self, key: str, content: bytes) -> tuple:
        """Upload content to S3. Returns (success, error)."""
        try:
            import boto3  # type: ignore
            client = boto3.client("s3", region_name=self._region)
            client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=content,
                ContentType="application/x-ndjson",
            )
            return True, None
        except ImportError:
            return False, "boto3 not installed — use local_fallback_dir for testing"
        except Exception as e:
            return False, str(e)

    def _write_local(self, key: str, content: str) -> None:
        """Write content to local filesystem (for dev/test)."""
        path = Path(self._local_dir) / key  # type: ignore
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
