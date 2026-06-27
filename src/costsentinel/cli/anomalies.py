"""CLI command for displaying detected cost anomalies.

Provides the 'costsentinel anomalies' command to show detected anomalies
with severity, timestamps, and recommended actions.

Usage:
    costsentinel anomalies --last 24h
    costsentinel anomalies --last 7d --severity critical
    costsentinel anomalies --last 1h --scope team --id engineering
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from costsentinel.core.config import load_config


@dataclass
class AnomalyRecord:
    """A stored anomaly detection record."""

    timestamp: float
    severity: str  # "warning", "critical"
    scope: str  # "global", "team", "user", "endpoint"
    scope_id: str
    message: str
    current_value: float
    baseline_value: float
    deviation_factor: float
    recommended_action: str

    @classmethod
    def from_dict(cls, data: dict) -> "AnomalyRecord":
        """Create from dictionary."""
        return cls(
            timestamp=data["timestamp"],
            severity=data["severity"],
            scope=data["scope"],
            scope_id=data["scope_id"],
            message=data["message"],
            current_value=data["current_value"],
            baseline_value=data["baseline_value"],
            deviation_factor=data["deviation_factor"],
            recommended_action=data.get("recommended_action", "Investigate"),
        )


def parse_time_range(time_str: str) -> float:
    """Parse a time range string into seconds.

    Supports: 1h, 2h, 24h, 1d, 7d, 30d, 1w

    Args:
        time_str: Time range string (e.g., "24h", "7d", "1w").

    Returns:
        Number of seconds in the range.

    Raises:
        ValueError: If the format is unrecognized.
    """
    time_str = time_str.strip().lower()

    multipliers = {
        "h": 3600,
        "d": 86400,
        "w": 604800,
    }

    for suffix, multiplier in multipliers.items():
        if time_str.endswith(suffix):
            try:
                value = int(time_str[:-len(suffix)])
                return value * multiplier
            except ValueError:
                raise ValueError(f"Invalid time value: {time_str}")

    raise ValueError(
        f"Unrecognized time format: '{time_str}'. "
        f"Use format like '24h', '7d', or '1w'."
    )


def load_anomalies(
    anomalies_file: str = ".costsentinel/anomalies.json",
) -> List[AnomalyRecord]:
    """Load anomaly records from the state file.

    Args:
        anomalies_file: Path to the anomalies JSON file.

    Returns:
        List of AnomalyRecord instances.
    """
    path = Path(anomalies_file)
    if not path.exists():
        return []

    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return []

    records = []
    for entry in data if isinstance(data, list) else data.get("anomalies", []):
        try:
            records.append(AnomalyRecord.from_dict(entry))
        except (KeyError, TypeError):
            continue

    return records


def filter_anomalies(
    records: List[AnomalyRecord],
    time_range_seconds: float,
    severity: Optional[str] = None,
    scope: Optional[str] = None,
    scope_id: Optional[str] = None,
) -> List[AnomalyRecord]:
    """Filter anomaly records by time range, severity, and scope.

    Args:
        records: All anomaly records.
        time_range_seconds: How far back to look.
        severity: Filter by severity (warning, critical).
        scope: Filter by scope (global, team, user, endpoint).
        scope_id: Filter by scope ID.

    Returns:
        Filtered list of records.
    """
    cutoff = time.time() - time_range_seconds
    filtered = [r for r in records if r.timestamp >= cutoff]

    if severity:
        filtered = [r for r in filtered if r.severity == severity.lower()]

    if scope:
        filtered = [r for r in filtered if r.scope == scope.lower()]

    if scope_id:
        filtered = [r for r in filtered if r.scope_id == scope_id]

    # Sort by timestamp descending (most recent first)
    filtered.sort(key=lambda r: r.timestamp, reverse=True)

    return filtered


def format_anomaly_table(records: List[AnomalyRecord]) -> str:
    """Format anomaly records as a CLI table.

    Args:
        records: Anomaly records to display.

    Returns:
        Formatted table string.
    """
    if not records:
        return "No anomalies detected in the specified time range."

    lines: List[str] = []
    lines.append("")
    lines.append(f"  {'SEVERITY':<10} {'TIME':<20} {'SCOPE':<15} {'DEVIATION':<12} {'MESSAGE'}")
    lines.append(f"  {'─' * 10} {'─' * 20} {'─' * 15} {'─' * 12} {'─' * 40}")

    for record in records:
        dt = datetime.fromtimestamp(record.timestamp, tz=timezone.utc)
        time_str = dt.strftime("%Y-%m-%d %H:%M")
        severity_icon = "🔴" if record.severity == "critical" else "🟡"
        scope_str = f"{record.scope}:{record.scope_id}"
        deviation_str = f"{record.deviation_factor:.1f}x"

        lines.append(
            f"  {severity_icon} {record.severity:<8} "
            f"{time_str:<20} "
            f"{scope_str:<15} "
            f"{deviation_str:<12} "
            f"{record.message}"
        )

    lines.append("")
    lines.append(f"  Total: {len(records)} anomalies")

    # Summary by severity
    critical_count = sum(1 for r in records if r.severity == "critical")
    warning_count = sum(1 for r in records if r.severity == "warning")
    if critical_count > 0:
        lines.append(f"  🔴 Critical: {critical_count}")
    if warning_count > 0:
        lines.append(f"  🟡 Warning: {warning_count}")

    lines.append("")

    # Add recommendations for critical anomalies
    critical_records = [r for r in records if r.severity == "critical"]
    if critical_records:
        lines.append("  Recommended Actions:")
        for record in critical_records[:3]:  # Top 3
            lines.append(f"    → {record.recommended_action}")
        lines.append("")

    return "\n".join(lines)


def anomalies_command(args: argparse.Namespace) -> int:
    """Execute the anomalies command.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Exit code (0=success, 1=anomalies found, 2=error).
    """
    try:
        time_range = parse_time_range(args.last)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    # Load anomalies
    anomalies_file = getattr(args, "file", ".costsentinel/anomalies.json")
    records = load_anomalies(anomalies_file)

    # Filter
    filtered = filter_anomalies(
        records=records,
        time_range_seconds=time_range,
        severity=getattr(args, "severity", None),
        scope=getattr(args, "scope", None),
        scope_id=getattr(args, "id", None),
    )

    # Output
    output_format = getattr(args, "format", "table")
    if output_format == "json":
        output = json.dumps(
            [
                {
                    "timestamp": r.timestamp,
                    "severity": r.severity,
                    "scope": r.scope,
                    "scope_id": r.scope_id,
                    "message": r.message,
                    "current_value": r.current_value,
                    "baseline_value": r.baseline_value,
                    "deviation_factor": r.deviation_factor,
                    "recommended_action": r.recommended_action,
                }
                for r in filtered
            ],
            indent=2,
        )
        print(output)
    else:
        print(format_anomaly_table(filtered))

    # Return 1 if critical anomalies found (useful for CI/CD gates)
    has_critical = any(r.severity == "critical" for r in filtered)
    return 1 if has_critical else 0


def register_anomalies_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the anomalies subcommand with argparse.

    Args:
        subparsers: The subparsers action from the parent parser.
    """
    parser = subparsers.add_parser(
        "anomalies",
        help="Show detected cost anomalies",
        description="Display cost anomalies with severity and recommended actions.",
    )
    parser.add_argument(
        "--last",
        required=True,
        help="Time range to query (e.g., 1h, 24h, 7d, 30d)",
    )
    parser.add_argument(
        "--severity",
        choices=["warning", "critical"],
        help="Filter by severity level",
    )
    parser.add_argument(
        "--scope",
        choices=["global", "team", "user", "endpoint"],
        help="Filter by cost scope",
    )
    parser.add_argument(
        "--id",
        help="Filter by scope ID (e.g., team name, user ID)",
    )
    parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--file",
        default=".costsentinel/anomalies.json",
        help="Path to anomalies state file",
    )
    parser.set_defaults(func=anomalies_command)
