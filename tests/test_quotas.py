"""Tests for token quota enforcement."""

import tempfile
from pathlib import Path

from costsentinel.policies.quotas import TokenQuotaEnforcer, QuotaDecision


class TestTokenQuotaEnforcer:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self.enforcer = TokenQuotaEnforcer(
            default_daily_limit=1000,
            user_limits={"vip-user": 5000},
            storage_path=self.tmp.name,
        )

    def teardown_method(self):
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_new_user_has_full_quota(self):
        decision = self.enforcer.check_quota("user-1", 100)
        assert decision.allowed is True
        assert decision.remaining == 1000
        assert decision.used == 0

    def test_record_usage_reduces_remaining(self):
        self.enforcer.record_usage("user-1", 300)
        decision = self.enforcer.check_quota("user-1", 0)
        assert decision.used == 300
        assert decision.remaining == 700

    def test_exceeding_quota_blocked(self):
        self.enforcer.record_usage("user-2", 900)
        decision = self.enforcer.check_quota("user-2", 200)
        assert decision.allowed is False

    def test_exactly_at_limit_allowed(self):
        self.enforcer.record_usage("user-3", 500)
        decision = self.enforcer.check_quota("user-3", 500)
        assert decision.allowed is True

    def test_custom_user_limit(self):
        decision = self.enforcer.check_quota("vip-user", 3000)
        assert decision.allowed is True
        assert decision.limit == 5000

    def test_get_usage(self):
        self.enforcer.record_usage("user-4", 250)
        usage = self.enforcer.get_usage("user-4")
        assert usage["used"] == 250
        assert usage["limit"] == 1000
        assert usage["remaining"] == 750

    def test_multiple_records_accumulate(self):
        self.enforcer.record_usage("user-5", 100)
        self.enforcer.record_usage("user-5", 200)
        self.enforcer.record_usage("user-5", 300)
        decision = self.enforcer.check_quota("user-5", 0)
        assert decision.used == 600

    def test_zero_estimated_tokens(self):
        decision = self.enforcer.check_quota("user-6", 0)
        assert decision.allowed is True

    def test_decision_has_correct_limit(self):
        decision = self.enforcer.check_quota("user-7", 0)
        assert decision.limit == 1000

    def test_persistence(self):
        self.enforcer.record_usage("persist-user", 500)
        enforcer2 = TokenQuotaEnforcer(
            default_daily_limit=1000,
            storage_path=self.tmp.name,
        )
        decision = enforcer2.check_quota("persist-user", 0)
        assert decision.used == 500
