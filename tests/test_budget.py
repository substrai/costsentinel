"""Tests for budget enforcement."""

import pytest

from costsentinel.core.config import CostSentinelConfig, PolicyConfig
from costsentinel.core.state import CostState
from costsentinel.policies.budget import BudgetDecision, BudgetEnforcer, BudgetExceededError


class TestBudgetEnforcer:
    """Test suite for BudgetEnforcer."""

    @pytest.fixture
    def state(self, tmp_path):
        """Create a CostState with a temporary file."""
        return CostState(str(tmp_path / "budget_state.json"))

    @pytest.fixture
    def config_with_policies(self):
        """Create a config with budget policies."""
        return CostSentinelConfig(
            project_name="test",
            policies=[
                PolicyConfig(
                    scope="global",
                    limit_daily=100.0,
                    limit_monthly=2000.0,
                    on_exceed="block",
                ),
                PolicyConfig(
                    scope="team",
                    limit_daily=25.0,
                    limit_monthly=500.0,
                    on_exceed="downgrade",
                ),
                PolicyConfig(
                    scope="user",
                    limit_daily=5.0,
                    limit_monthly=100.0,
                    on_exceed="block",
                    max_cost_per_request=0.50,
                ),
            ],
        )

    def test_allow_within_budget(self, config_with_policies, state):
        enforcer = BudgetEnforcer(config_with_policies, state)
        decision = enforcer.check("global", "default", 1.0)

        assert decision.allowed is True
        assert decision.action == "allow"
        assert decision.remaining == 100.0

    def test_block_daily_exceeded(self, config_with_policies, state):
        enforcer = BudgetEnforcer(config_with_policies, state)

        # Spend up to the limit
        state.increment("global", "default", 99.5)

        decision = enforcer.check("global", "default", 1.0)
        assert decision.allowed is False
        assert decision.action == "block"
        assert "Daily budget exceeded" in decision.reason

    def test_block_monthly_exceeded(self, state):
        # Use a config where daily limit is high but monthly is low
        config = CostSentinelConfig(
            project_name="test",
            policies=[
                PolicyConfig(
                    scope="global",
                    limit_daily=5000.0,
                    limit_monthly=2000.0,
                    on_exceed="block",
                ),
            ],
        )
        enforcer = BudgetEnforcer(config, state)

        # Spend up to the monthly limit (within daily)
        state.increment("global", "default", 1999.5)

        decision = enforcer.check("global", "default", 1.0)
        assert decision.allowed is False
        assert decision.action == "block"
        assert "Monthly budget exceeded" in decision.reason

    def test_downgrade_action(self, config_with_policies, state):
        enforcer = BudgetEnforcer(config_with_policies, state)

        # Exceed team daily limit
        state.increment("team", "team-alpha", 24.5)

        decision = enforcer.check("team", "team-alpha", 1.0)
        assert decision.allowed is False
        assert decision.action == "downgrade"

    def test_max_cost_per_request(self, config_with_policies, state):
        enforcer = BudgetEnforcer(config_with_policies, state)

        # Request that exceeds per-request limit
        decision = enforcer.check("user", "user-1", 0.75)
        assert decision.allowed is False
        assert decision.action == "block"
        assert "per-request limit" in decision.reason

    def test_no_policy_allows(self, state):
        config = CostSentinelConfig(project_name="test", policies=[])
        enforcer = BudgetEnforcer(config, state)

        decision = enforcer.check("global", "default", 1000.0)
        assert decision.allowed is True
        assert decision.action == "allow"

    def test_remaining_budget_calculation(self, config_with_policies, state):
        enforcer = BudgetEnforcer(config_with_policies, state)

        state.increment("global", "default", 30.0)
        decision = enforcer.check("global", "default", 1.0)

        assert decision.allowed is True
        assert decision.remaining == pytest.approx(70.0, abs=0.01)

    def test_budget_decision_dataclass(self):
        decision = BudgetDecision(
            allowed=True,
            action="allow",
            reason="Within budget",
            remaining=50.0,
            limit=100.0,
        )
        assert decision.allowed is True
        assert decision.remaining == 50.0

    def test_budget_exceeded_error(self):
        error = BudgetExceededError(
            "Budget exceeded", scope="user", limit=5.0, current=5.5
        )
        assert str(error) == "Budget exceeded"
        assert error.scope == "user"
        assert error.limit == 5.0
        assert error.current == 5.5

    def test_exactly_at_limit_blocks(self, config_with_policies, state):
        enforcer = BudgetEnforcer(config_with_policies, state)

        # Spend exactly the daily limit
        state.increment("user", "user-1", 5.0)

        # Even a tiny cost should be blocked
        decision = enforcer.check("user", "user-1", 0.001)
        assert decision.allowed is False
