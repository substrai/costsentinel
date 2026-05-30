"""Tests for rate limiter integration in middleware."""

import pytest
import tempfile
import os

from costsentinel.core.config import CostSentinelConfig, PolicyConfig
from costsentinel.middleware.interceptor import CostMiddleware, RateLimitExceededError


@pytest.fixture
def middleware(tmp_path):
    """Create middleware with low rate limits for testing."""
    config = CostSentinelConfig(
        project_name="test",
        pricing={"test-model": {"input": 0.001, "output": 0.002}},
        rate_limits={"requests_per_minute": 3, "per_user_rpm": 2, "per_team_rpm": 2},
        state_file=str(tmp_path / "state.json"),
        attribution_file=str(tmp_path / "attr.json"),
    )
    return CostMiddleware(config)


def test_rate_limit_allows_within_limit(middleware):
    """Requests within limit should pass."""
    middleware.check_rate_limit(user_id="user-1")
    middleware.check_rate_limit(user_id="user-1")
    # 2 requests allowed for per_user_rpm=2


def test_rate_limit_blocks_over_limit(middleware):
    """Requests over limit should raise RateLimitExceededError."""
    middleware.check_rate_limit(user_id="user-1")
    middleware.check_rate_limit(user_id="user-1")
    with pytest.raises(RateLimitExceededError) as exc_info:
        middleware.check_rate_limit(user_id="user-1")
    assert exc_info.value.scope == "user"
    assert exc_info.value.scope_id == "user-1"


def test_rate_limit_global_blocks(middleware):
    """Global rate limit should block after 3 requests."""
    middleware.check_rate_limit(user_id="user-1")
    middleware.check_rate_limit(user_id="user-2")
    middleware.check_rate_limit(user_id="user-3")
    with pytest.raises(RateLimitExceededError) as exc_info:
        middleware.check_rate_limit(user_id="user-4")
    assert exc_info.value.scope == "global"


def test_rate_limit_team_isolation(middleware):
    """Different teams should have independent limits."""
    middleware.check_rate_limit(team_id="team-a")
    middleware.check_rate_limit(team_id="team-a")
    with pytest.raises(RateLimitExceededError):
        middleware.check_rate_limit(team_id="team-a")
    # team-b should still be allowed
    middleware.check_rate_limit(team_id="team-b")


def test_rate_limit_no_user_or_team(middleware):
    """Should only check global limit when no user/team specified."""
    middleware.check_rate_limit()
    middleware.check_rate_limit()
    middleware.check_rate_limit()
    with pytest.raises(RateLimitExceededError):
        middleware.check_rate_limit()


def test_rate_limiter_accessible(middleware):
    """Rate limiter should be accessible via property."""
    assert middleware.rate_limiter is not None
    remaining = middleware.rate_limiter.get_remaining("global", "default")
    assert remaining >= 0
