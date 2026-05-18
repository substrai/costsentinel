"""Tests for gradual degradation."""

from costsentinel.routing.degradation import GradualDegrader


class TestGradualDegrader:
    def setup_method(self):
        self.degrader = GradualDegrader()

    def test_level_0_when_plenty_remaining(self):
        assert self.degrader.get_degradation_level(0.80) == 0

    def test_level_1_when_moderate_remaining(self):
        assert self.degrader.get_degradation_level(0.35) == 1

    def test_level_2_when_low_remaining(self):
        assert self.degrader.get_degradation_level(0.10) == 2

    def test_level_3_when_zero_remaining(self):
        assert self.degrader.get_degradation_level(0.0) == 3

    def test_premium_model_at_high_budget(self):
        model = self.degrader.get_model(0.75)
        assert model == "claude-3.5-sonnet"

    def test_standard_model_at_moderate_budget(self):
        model = self.degrader.get_model(0.40)
        assert model == "claude-3-sonnet"

    def test_economy_model_at_low_budget(self):
        model = self.degrader.get_model(0.15)
        assert model == "claude-3-haiku"

    def test_blocked_at_zero(self):
        assert self.degrader.is_blocked(0.0) is True
        assert self.degrader.get_model(0.0) == ""

    def test_not_blocked_with_budget(self):
        assert self.degrader.is_blocked(0.5) is False

    def test_custom_boundaries(self):
        degrader = GradualDegrader(boundaries=[0.70, 0.30, 0.0])
        assert degrader.get_degradation_level(0.80) == 0
        assert degrader.get_degradation_level(0.50) == 1
        assert degrader.get_degradation_level(0.20) == 2

    def test_custom_models(self):
        degrader = GradualDegrader(models={0: "gpt-4", 1: "gpt-3.5", 2: "gpt-mini", 3: ""})
        assert degrader.get_model(0.80) == "gpt-4"
        assert degrader.get_model(0.10) == "gpt-mini"
