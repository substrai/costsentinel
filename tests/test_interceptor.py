"""Tests for the middleware interceptor."""

import pytest

from costsentinel.core.config import CostSentinelConfig, PolicyConfig
from costsentinel.core.state import CostState
from costsentinel.middleware.interceptor import CallResult, CostMiddleware
from costsentinel.policies.budget import BudgetExceededError


class TestCostMiddleware:
    """Test suite for CostMiddleware."""

    @pytest.fixture
    def config(self, tmp_path):
        """Create a test config."""
        return CostSentinelConfig(
            project_name="test",
            pricing={
                "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
                "claude-3.5-sonnet": {"input": 0.003, "output": 0.015},
            },
            policies=[
                PolicyConfig(
                    scope="global",
                    limit_daily=100.0,
                    limit_monthly=2000.0,
                    on_exceed="block",
                ),
                PolicyConfig(
                    scope="user",
                    limit_daily=5.0,
                    limit_monthly=100.0,
                    on_exceed="block",
                ),
            ],
            state_file=str(tmp_path / "state.json"),
            attribution_file=str(tmp_path / "attr.json"),
        )

    @pytest.fixture
    def middleware(self, config):
        """Create a CostMiddleware instance."""
        return CostMiddleware(config)

    def test_intercept_decorator(self, middleware):
        @middleware.intercept(model="claude-3-haiku", user_id="user-1")
        def mock_llm_call(prompt):
            return "response text", 100, 50

        result = mock_llm_call("hello")
        assert isinstance(result, CallResult)
        assert result.response == "response text"
        assert result.tokens_in == 100
        assert result.tokens_out == 50
        assert result.model_used == "claude-3-haiku"
        assert result.cost > 0

    def test_intercept_calculates_correct_cost(self, middleware):
        @middleware.intercept(model="claude-3-haiku", user_id="user-1")
        def mock_call(prompt):
            return "ok", 1000, 500

        result = mock_call("test")
        # 1000 input * 0.00025/1K + 500 output * 0.00125/1K
        expected = 0.00025 + 0.000625
        assert result.cost == pytest.approx(expected, abs=1e-6)

    def test_track_call_manual(self, middleware):
        result = middleware.track_call(
            model="claude-3-haiku",
            input_tokens=500,
            output_tokens=200,
            metadata={"user_id": "user-1", "team_id": "team-a"},
        )
        assert isinstance(result, CallResult)
        assert result.cost > 0
        assert result.tokens_in == 500
        assert result.tokens_out == 200

    def test_track_call_updates_state(self, middleware):
        middleware.track_call(
            model="claude-3-haiku",
            input_tokens=1000,
            output_tokens=500,
            metadata={"user_id": "user-1"},
        )

        # Check state was updated
        total = middleware.state.get_total("global", "default", "daily")
        assert total > 0

        user_total = middleware.state.get_total("user", "user-1", "daily")
        assert user_total > 0

    def test_budget_enforcement_blocks(self, middleware):
        # Exhaust user budget
        for _ in range(100):
            try:
                middleware.track_call(
                    model="claude-3.5-sonnet",
                    input_tokens=10000,
                    output_tokens=5000,
                    metadata={"user_id": "big-spender"},
                )
            except BudgetExceededError:
                break
        else:
            pytest.fail("Expected BudgetExceededError to be raised")

    def test_intercept_non_tuple_response(self, middleware):
        @middleware.intercept(model="claude-3-haiku", user_id="user-1")
        def mock_call(prompt):
            return "just a string"

        result = mock_call("test")
        assert result.response == "just a string"
        assert result.tokens_in == 0
        assert result.tokens_out == 0

    def test_call_result_has_duration(self, middleware):
        @middleware.intercept(model="claude-3-haiku", user_id="user-1")
        def mock_call(prompt):
            return "ok", 100, 50

        result = mock_call("test")
        assert result.duration_ms >= 0

    def test_middleware_properties(self, middleware, config):
        assert middleware.config == config
        assert middleware.pricing is not None
        assert middleware.state is not None
        assert middleware.budget is not None
