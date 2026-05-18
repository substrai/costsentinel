"""Tests for anomaly detector."""

import tempfile
from pathlib import Path

from costsentinel.detection.baseline import BaselineLearner
from costsentinel.detection.anomaly import AnomalyDetector, AnomalyAlert


class TestAnomalyDetector:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self.learner = BaselineLearner(storage_path=self.tmp.name)
        # Build a baseline
        for i in range(20):
            self.learner.record("endpoint:/api/chat", cost=0.01, tokens=100)
        self.detector = AnomalyDetector(self.learner, spike_multiplier=3.0, warning_multiplier=2.0)

    def teardown_method(self):
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_no_alert_for_normal_rate(self):
        baseline = self.learner.get_baseline("endpoint:/api/chat")
        normal_rate = baseline.mean_cost_per_hour
        alert = self.detector.check_cost_rate("endpoint:/api/chat", normal_rate)
        assert alert is None

    def test_warning_for_2x_rate(self):
        baseline = self.learner.get_baseline("endpoint:/api/chat")
        high_rate = baseline.mean_cost_per_hour * 2.5
        alert = self.detector.check_cost_rate("endpoint:/api/chat", high_rate)
        assert alert is not None
        assert alert.severity == "warning"

    def test_critical_for_3x_rate(self):
        baseline = self.learner.get_baseline("endpoint:/api/chat")
        spike_rate = baseline.mean_cost_per_hour * 4.0
        alert = self.detector.check_cost_rate("endpoint:/api/chat", spike_rate)
        assert alert is not None
        assert alert.severity == "critical"

    def test_no_alert_without_baseline(self):
        alert = self.detector.check_cost_rate("unknown:scope", 100.0)
        assert alert is None

    def test_token_ratio_normal(self):
        alert = self.detector.check_token_ratio("user:1", input_tokens=100, output_tokens=200)
        assert alert is None

    def test_token_ratio_warning(self):
        alert = self.detector.check_token_ratio("user:1", input_tokens=100, output_tokens=600)
        assert alert is not None
        assert alert.severity == "warning"

    def test_token_ratio_critical(self):
        alert = self.detector.check_token_ratio("user:1", input_tokens=100, output_tokens=1500)
        assert alert is not None
        assert alert.severity == "critical"
        assert "prompt injection" in alert.message.lower()

    def test_token_ratio_zero_input(self):
        alert = self.detector.check_token_ratio("user:1", input_tokens=0, output_tokens=500)
        assert alert is None

    def test_runaway_session_detected(self):
        alert = self.detector.check_session_runaway("sess-1", session_cost=3.0, session_duration_seconds=400)
        assert alert is not None
        assert alert.alert_type == "runaway_session"

    def test_runaway_session_not_triggered_short(self):
        alert = self.detector.check_session_runaway("sess-2", session_cost=3.0, session_duration_seconds=100)
        assert alert is None

    def test_runaway_session_not_triggered_cheap(self):
        alert = self.detector.check_session_runaway("sess-3", session_cost=0.50, session_duration_seconds=600)
        assert alert is None

    def test_get_recent_alerts(self):
        baseline = self.learner.get_baseline("endpoint:/api/chat")
        self.detector.check_cost_rate("endpoint:/api/chat", baseline.mean_cost_per_hour * 4)
        alerts = self.detector.get_recent_alerts()
        assert len(alerts) >= 1

    def test_get_alerts_by_severity(self):
        self.detector.check_token_ratio("user:x", 10, 200)
        critical = self.detector.get_alerts_by_severity("critical")
        assert all(a.severity == "critical" for a in critical)
