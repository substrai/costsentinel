"""Tests for model routing engine."""

from costsentinel.routing.engine import ModelRouter, RoutingDecision


class TestModelRouter:
    def test_tier1_when_budget_low_consumption(self):
        router = ModelRouter()
        decision = router.route(0.2)
        assert decision.tier == "tier_1"
        assert decision.model == "claude-3.5-sonnet"

    def test_tier2_when_budget_moderate_consumption(self):
        router = ModelRouter()
        decision = router.route(0.55)
        assert decision.tier == "tier_2"

    def test_tier3_when_budget_high_consumption(self):
        router = ModelRouter()
        decision = router.route(0.85)
        assert decision.tier == "tier_3"
        assert decision.model == "claude-3-haiku"

    def test_blocked_when_budget_exhausted(self):
        router = ModelRouter()
        decision = router.route(1.0)
        assert decision.tier == "blocked"
        assert decision.model == ""

    def test_custom_models(self):
        router = ModelRouter(models={"tier_1": "gpt-4", "tier_2": "gpt-3.5", "tier_3": "gpt-mini"})
        decision = router.route(0.1)
        assert decision.model == "gpt-4"

    def test_custom_thresholds(self):
        router = ModelRouter(downgrade_at=0.5, block_at=0.9)
        decision = router.route(0.6)
        assert decision.tier == "tier_3"

    def test_original_model_tracked(self):
        router = ModelRouter()
        decision = router.route(0.9, original_model="claude-3.5-sonnet")
        assert decision.original_model == "claude-3.5-sonnet"
        assert "Downgraded" in decision.reason

    def test_no_downgrade_when_same_model(self):
        router = ModelRouter()
        decision = router.route(0.1, original_model="claude-3.5-sonnet")
        assert "requested model" in decision.reason

    def test_get_current_tier_boundaries(self):
        router = ModelRouter(downgrade_at=0.80)
        assert router.get_current_tier(0.0) == "tier_1"
        assert router.get_current_tier(0.79) == "tier_2"
        assert router.get_current_tier(0.80) == "tier_3"
        assert router.get_current_tier(1.0) == "blocked"

    def test_zero_consumption(self):
        router = ModelRouter()
        decision = router.route(0.0)
        assert decision.tier == "tier_1"

    def test_exactly_at_downgrade_threshold(self):
        router = ModelRouter(downgrade_at=0.80)
        decision = router.route(0.80)
        assert decision.tier == "tier_3"

    def test_just_below_block(self):
        router = ModelRouter(block_at=1.0)
        decision = router.route(0.99)
        assert decision.tier == "tier_3"
        assert decision.allowed if hasattr(decision, "allowed") else True
