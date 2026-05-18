"""Compliance mode - audit-ready logging with tamper-proof records."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ComplianceRecord:
    """A tamper-evident compliance record."""

    record_id: str
    timestamp: float
    event_type: str
    data: Dict[str, Any]
    previous_hash: str
    record_hash: str


class ComplianceLogger:
    """Audit-ready logging with hash-chain integrity verification.

    Each record includes a hash of the previous record, creating a
    tamper-evident chain similar to a blockchain. Any modification
    to historical records breaks the chain and is detectable.
    """

    def __init__(self, storage_path: str | Path = ".costsentinel_compliance.jsonl"):
        self.storage_path = Path(storage_path)
        self._records: List[ComplianceRecord] = []
        self._last_hash: str = "genesis"
        self._load()

    def _load(self) -> None:
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            data = json.loads(line)
                            record = ComplianceRecord(**data)
                            self._records.append(record)
                            self._last_hash = record.record_hash
            except (json.JSONDecodeError, IOError):
                pass

    def _compute_hash(self, record_id: str, timestamp: float, event_type: str, data: Dict, previous_hash: str) -> str:
        """Compute SHA-256 hash for a record."""
        payload = f"{record_id}|{timestamp}|{event_type}|{json.dumps(data, sort_keys=True)}|{previous_hash}"
        return hashlib.sha256(payload.encode()).hexdigest()

    def log(self, event_type: str, data: Dict[str, Any]) -> ComplianceRecord:
        """Log a compliance event with hash-chain integrity.

        Args:
            event_type: Type of event (e.g., "budget_check", "cost_recorded", "policy_change").
            data: Event data to log.

        Returns:
            The created ComplianceRecord.
        """
        timestamp = time.time()
        record_id = f"{event_type}-{int(timestamp * 1000)}"

        record_hash = self._compute_hash(record_id, timestamp, event_type, data, self._last_hash)

        record = ComplianceRecord(
            record_id=record_id,
            timestamp=timestamp,
            event_type=event_type,
            data=data,
            previous_hash=self._last_hash,
            record_hash=record_hash,
        )

        self._records.append(record)
        self._last_hash = record_hash
        self._append_to_file(record)

        return record

    def _append_to_file(self, record: ComplianceRecord) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, "a") as f:
            f.write(json.dumps({
                "record_id": record.record_id,
                "timestamp": record.timestamp,
                "event_type": record.event_type,
                "data": record.data,
                "previous_hash": record.previous_hash,
                "record_hash": record.record_hash,
            }) + "\n")

    def verify_integrity(self) -> bool:
        """Verify the hash chain integrity of all records.

        Returns:
            True if chain is intact, False if tampering detected.
        """
        if not self._records:
            return True

        expected_prev = "genesis"
        for record in self._records:
            if record.previous_hash != expected_prev:
                return False

            computed = self._compute_hash(
                record.record_id, record.timestamp,
                record.event_type, record.data, record.previous_hash,
            )
            if computed != record.record_hash:
                return False

            expected_prev = record.record_hash

        return True

    def get_records(
        self,
        event_type: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
    ) -> List[ComplianceRecord]:
        """Query compliance records with optional filters.

        Args:
            event_type: Filter by event type.
            start_time: Filter records after this timestamp.
            end_time: Filter records before this timestamp.

        Returns:
            List of matching ComplianceRecord objects.
        """
        results = self._records

        if event_type:
            results = [r for r in results if r.event_type == event_type]
        if start_time:
            results = [r for r in results if r.timestamp >= start_time]
        if end_time:
            results = [r for r in results if r.timestamp <= end_time]

        return results

    @property
    def record_count(self) -> int:
        return len(self._records)
