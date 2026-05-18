"""Tests for multi-account aggregation."""

import tempfile
from pathlib import Path

from costsentinel.deployment.multi_account import MultiAccountAggregator


class TestMultiAccountAggregator:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self.agg = MultiAccountAggregator(storage_path=self.tmp.name)

    def teardown_method(self):
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_register_account(self):
        self.agg.register_account("123456789", "Production")
        assert "123456789" in self.agg.get_registered_accounts()

    def test_record_cost(self):
        self.agg.register_account("111", "Dev")
        self.agg.record_cost("111", 5.50)
        total = self.agg.get_total_across_accounts()
        assert total == 5.50

    def test_multiple_accounts(self):
        self.agg.register_account("111", "Dev")
        self.agg.register_account("222", "Prod")
        self.agg.record_cost("111", 3.00)
        self.agg.record_cost("222", 7.00)
        total = self.agg.get_total_across_accounts()
        assert total == 10.00

    def test_per_account_summary(self):
        self.agg.register_account("111", "Dev")
        self.agg.register_account("222", "Prod")
        self.agg.record_cost("111", 2.00)
        self.agg.record_cost("222", 8.00)
        summary = self.agg.get_per_account_summary()
        assert len(summary) == 2
        assert summary[0].total_cost == 8.00  # Sorted descending

    def test_unregistered_account_auto_creates(self):
        self.agg.record_cost("999", 1.00)
        assert "999" in self.agg.get_registered_accounts()

    def test_persistence(self):
        self.agg.register_account("111", "Test")
        self.agg.record_cost("111", 4.00)
        agg2 = MultiAccountAggregator(storage_path=self.tmp.name)
        assert agg2.get_total_across_accounts() == 4.00

    def test_empty_total(self):
        assert self.agg.get_total_across_accounts() == 0.0

    def test_empty_summary(self):
        assert self.agg.get_per_account_summary() == []
