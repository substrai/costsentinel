"""Tests for circuit breaker integration in middleware."""

import pytest

from costsentinel.core.config import CostSentinelConfig, PolicyConfig
from costsentinel.middleware.interceptor import CostMiddleware
from costsentinel.policies.circuit_breaker import CircuitBreakerTripped


@pytest.fixture
def middleware(tmp_path):
    """Create middleware with circuit breaker configured."""
    config = CostSentinelConfig(
        project_name="test",
        pricing={"test-model": {"input": 0.001, "output": 0.002}},
        policies=[PolicyConfig(scope="global", limit_daily=100.0, max_cost_per_request=0.25)],
        state_file=str(tmp_path / "state.json"),
        attribution_file=str(tmp_path / "attr.json"),
    )
    return CostMiddleware(config)


def test_circuit_breaker_allows_within_limits(middleware):
    """Requests within limits should pass."""
    middleware.check_circuit_breaker(estimated_cost=0.10, input_tokens=500)


def test_circuit_breaker_blocks_expensive_request(middleware):
    """Requests exceeding per-request cost should be blocked."""
    with pytest.raises(CircuitBreakerTripped) as exc_info:
        middleware.check_circuit_breaker(estimated_cost=1.00, input_tokens=100)
    assert exc_info.value.threshold == 0.25
    assert exc_info.value.current == 1.00


def test_circuit_breaker_blocks_high_token_request(middleware):
    """Requests exceeding token limit should be blocked."""
    with pytest.raises(CircuitBreakerTripped):
        middleware.check_circuit_breaker(estimated_cost=0.01, input_tokens=10000)


def test_circuit_breaker_session_limit(middleware):
    """Session exceeding cumulative cost should be blocked."""
    cb = middleware.circuit_breaker
    # Simulate session accumulating cost
    cb._sessions["session-1"] = {"total_cost": 6.0}
    cb._save()

    with pytest.raises(CircuitBreakerTripped) as exc_info:
        middleware.check_circuit_breaker(
            estimated_cost=0.01, input_tokens=100, session_id="session-1"
        )
    assert "Session cost" in str(exc_info.value)


def test_circuit_breaker_no_session_check_without_id(middleware):
    """Without session_id, only per-request checks run."""
    middleware.check_circuit_breaker(estimated_cost=0.10, input_tokens=500)


def test_circuit_breaker_accessible(middleware):
    """Circuit breaker should be accessible via property."""
    assert middleware.circuit_breaker is not None
    assert middleware.circuit_breaker.max_cost_per_request == 0.25
