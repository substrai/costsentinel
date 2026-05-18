"""Tests for compliance logging with hash-chain integrity."""

import tempfile
from pathlib import Path

from costsentinel.deployment.compliance import ComplianceLogger


class TestComplianceLogger:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
        self.tmp.close()
        self.logger = ComplianceLogger(storage_path=self.tmp.name)

    def teardown_method(self):
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_log_creates_record(self):
        record = self.logger.log("budget_check", {"user": "u1", "allowed": True})
        assert record.event_type == "budget_check"
        assert record.record_hash != ""

    def test_record_count(self):
        self.logger.log("event_a", {"x": 1})
        self.logger.log("event_b", {"x": 2})
        assert self.logger.record_count == 2

    def test_hash_chain_integrity(self):
        self.logger.log("e1", {"a": 1})
        self.logger.log("e2", {"b": 2})
        self.logger.log("e3", {"c": 3})
        assert self.logger.verify_integrity() is True

    def test_genesis_hash(self):
        record = self.logger.log("first", {})
        assert record.previous_hash == "genesis"

    def test_chain_links(self):
        r1 = self.logger.log("e1", {"x": 1})
        r2 = self.logger.log("e2", {"x": 2})
        assert r2.previous_hash == r1.record_hash

    def test_get_records_by_type(self):
        self.logger.log("budget_check", {"a": 1})
        self.logger.log("cost_recorded", {"b": 2})
        self.logger.log("budget_check", {"c": 3})
        results = self.logger.get_records(event_type="budget_check")
        assert len(results) == 2

    def test_get_records_all(self):
        self.logger.log("e1", {})
        self.logger.log("e2", {})
        results = self.logger.get_records()
        assert len(results) == 2

    def test_persistence(self):
        self.logger.log("persist_test", {"data": "value"})
        logger2 = ComplianceLogger(storage_path=self.tmp.name)
        assert logger2.record_count == 1
        assert logger2.verify_integrity() is True

    def test_empty_log_integrity(self):
        assert self.logger.verify_integrity() is True

    def test_record_has_timestamp(self):
        record = self.logger.log("test", {"key": "val"})
        assert record.timestamp > 0

    def test_unique_hashes(self):
        r1 = self.logger.log("e1", {"x": 1})
        r2 = self.logger.log("e2", {"x": 2})
        assert r1.record_hash != r2.record_hash
