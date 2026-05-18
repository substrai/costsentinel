"""Tests for rate limiter."""

import time
import tempfile
from pathlib import Path

from costsentinel.policies.rate_limit import RateLimiter, RateLimitDecision


class TestRateLimiter:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self.limiter = RateLimiter(
            global_rpm=60, per_user_rpm=10, per_team_rpm=30,
            storage_path=self.tmp.name,
        )

    def teardown_method(self):
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_first_request_allowed(self):
        decision = self.limiter.check("user", "user-1")
        assert decision.allowed is True
        assert decision.remaining > 0

    def test_consume_reduces_tokens(self):
        initial = self.limiter.get_remaining("user", "user-1")
        self.limiter.consume("user", "user-1")
        after = self.limiter.get_remaining("user", "user-1")
        assert after == initial - 1

    def test_exhaust_tokens_blocks(self):
        # Consume all tokens
        for _ in range(10):
            self.limiter.consume("user", "user-2")
        decision = self.limiter.check("user", "user-2")
        assert decision.allowed is False
        assert decision.remaining == 0

    def test_different_users_independent(self):
        for _ in range(10):
            self.limiter.consume("user", "user-a")
        # user-b should still have tokens
        decision = self.limiter.check("user", "user-b")
        assert decision.allowed is True

    def test_different_scopes_independent(self):
        for _ in range(10):
            self.limiter.consume("user", "user-1")
        # Team scope should still have tokens
        decision = self.limiter.check("team", "team-1")
        assert decision.allowed is True

    def test_decision_has_limit(self):
        decision = self.limiter.check("user", "user-1")
        assert decision.limit == 10

    def test_global_scope(self):
        decision = self.limiter.check("global", "global")
        assert decision.limit == 60
        assert decision.allowed is True

    def test_consume_returns_false_when_empty(self):
        for _ in range(10):
            self.limiter.consume("user", "user-x")
        result = self.limiter.consume("user", "user-x")
        assert result is False

    def test_consume_returns_true_when_available(self):
        result = self.limiter.consume("user", "user-y")
        assert result is True

    def test_reset_at_is_future(self):
        decision = self.limiter.check("user", "user-1")
        assert decision.reset_at > time.time()

    def test_get_remaining_new_user(self):
        remaining = self.limiter.get_remaining("user", "new-user")
        assert remaining == 10

    def test_persistence(self):
        self.limiter.consume("user", "persist-user")
        # Create new limiter from same file
        limiter2 = RateLimiter(
            global_rpm=60, per_user_rpm=10, per_team_rpm=30,
            storage_path=self.tmp.name,
        )
        remaining = limiter2.get_remaining("user", "persist-user")
        assert remaining == 9
