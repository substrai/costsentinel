"""Tests for pattern-based detection."""

from costsentinel.detection.patterns import PatternDetector, DetectionRule


class TestPatternDetector:
    def setup_method(self):
        self.detector = PatternDetector()

    def test_repeated_expensive_detected(self):
        costs = [0.15, 0.12, 0.18, 0.11, 0.20]
        alert = self.detector.check_repeated_expensive("/api/chat", costs, threshold=0.10, min_consecutive=5)
        assert alert is not None
        assert alert.alert_type == "repeated_expensive"

    def test_repeated_expensive_not_triggered_below_threshold(self):
        costs = [0.05, 0.08, 0.03, 0.07, 0.04]
        alert = self.detector.check_repeated_expensive("/api/chat", costs, threshold=0.10, min_consecutive=5)
        assert alert is None

    def test_repeated_expensive_not_enough_calls(self):
        costs = [0.15, 0.12]
        alert = self.detector.check_repeated_expensive("/api/chat", costs, threshold=0.10, min_consecutive=5)
        assert alert is None

    def test_repeated_expensive_mixed_costs(self):
        costs = [0.15, 0.02, 0.18, 0.11, 0.20]
        alert = self.detector.check_repeated_expensive("/api/chat", costs, threshold=0.10, min_consecutive=5)
        assert alert is None  # Not all consecutive

    def test_off_hours_premium_detected(self):
        alert = self.detector.check_off_hours_premium("claude-3.5-sonnet", hour_of_day=2)
        assert alert is not None
        assert alert.alert_type == "off_hours_premium"

    def test_off_hours_premium_not_triggered_business_hours(self):
        alert = self.detector.check_off_hours_premium("claude-3.5-sonnet", hour_of_day=14)
        assert alert is None

    def test_off_hours_non_premium_not_triggered(self):
        alert = self.detector.check_off_hours_premium("claude-3-haiku", hour_of_day=2)
        assert alert is None

    def test_custom_business_hours(self):
        alert = self.detector.check_off_hours_premium(
            "claude-3.5-sonnet", hour_of_day=7, business_hours=(9, 17)
        )
        assert alert is not None

    def test_get_triggered_rules(self):
        self.detector.check_off_hours_premium("claude-3.5-sonnet", hour_of_day=3)
        triggered = self.detector.get_triggered_rules()
        assert len(triggered) == 1
        assert triggered[0]["rule"] == "off-hours-premium"

    def test_custom_premium_models(self):
        alert = self.detector.check_off_hours_premium(
            "my-custom-model", hour_of_day=2, premium_models=["my-custom-model"]
        )
        assert alert is not None
