"""Tests for circuit breaker."""

import tempfile
from pathlib import Path

from costsentinel.policies.circuit_breaker import CircuitBreaker, CircuitBreakerTripped, CircuitDecision


class TestCircuitBreaker:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self.cb = CircuitBreaker(
            max_cost_per_request=0.50,
            max_cost_per_session=5.00,
            max_tokens_per_request=8000,
            storage_path=self.tmp.name,
        )

    def teardown_method(self):
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_normal_request_allowed(self):
        decision = self.cb.check_request(estimated_cost=0.10, input_tokens=500)
        assert decision.allowed is True

    def test_expensive_request_blocked(self):
        decision = self.cb.check_request(estimated_cost=0.75, input_tokens=500)
        assert decision.allowed is False
        assert "exceeds limit" in decision.reason

    def test_too_many_tokens_blocked(self):
        decision = self.cb.check_request(estimated_cost=0.01, input_tokens=10000)
        assert decision.allowed is False
        assert "tokens" in decision.reason.lower()

    def test_session_within_limit(self):
        self.cb.record_session_cost("session-1", 1.00)
        decision = self.cb.check_session("session-1")
        assert decision.allowed is True

    def test_session_exceeds_limit(self):
        self.cb.record_session_cost("session-2", 3.00)
        self.cb.record_session_cost("session-2", 3.00)
        decision = self.cb.check_session("session-2")
        assert decision.allowed is False

    def test_session_cost_accumulates(self):
        self.cb.record_session_cost("session-3", 1.00)
        self.cb.record_session_cost("session-3", 1.50)
        assert self.cb.get_session_cost("session-3") == 2.50

    def test_new_session_zero_cost(self):
        assert self.cb.get_session_cost("new-session") == 0.0

    def test_reset_session(self):
        self.cb.record_session_cost("session-4", 3.00)
        self.cb.reset_session("session-4")
        assert self.cb.get_session_cost("session-4") == 0.0

    def test_exactly_at_request_limit(self):
        decision = self.cb.check_request(estimated_cost=0.50, input_tokens=100)
        assert decision.allowed is True  # Exactly at limit is allowed (> not >=)

    def test_zero_cost_allowed(self):
        decision = self.cb.check_request(estimated_cost=0.0, input_tokens=0)
        assert decision.allowed is True

    def test_persistence(self):
        self.cb.record_session_cost("persist-session", 2.50)
        cb2 = CircuitBreaker(storage_path=self.tmp.name)
        assert cb2.get_session_cost("persist-session") == 2.50
