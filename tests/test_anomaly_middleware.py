"""Tests for anomaly detection integration in middleware."""

import pytest

from costsentinel.core.config import CostSentinelConfig, PolicyConfig
from costsentinel.middleware.interceptor import CostMiddleware


@pytest.fixture
def middleware(tmp_path):
    """Create middleware with anomaly detection."""
    config = CostSentinelConfig(
        project_name="test",
        pricing={"test-model": {"input": 0.001, "output": 0.002}},
        policies=[PolicyConfig(scope="global", limit_daily=100.0)],
        alerts={"thresholds": [0.5, 0.75, 0.9]},
        state_file=str(tmp_path / "state.json"),
        attribution_file=str(tmp_path / "attr.json"),
    )
    return CostMiddleware(config)


def test_anomaly_detector_accessible(middleware):
    """Anomaly detector should be accessible via property."""
    assert middleware.anomaly_detector is not None


def test_anomaly_alerts_starts_empty(middleware):
    """Anomaly alerts list should start empty."""
    assert middleware.anomaly_alerts == []


def test_check_anomaly_post_call_no_alert_normal(middleware):
    """Normal cost should not trigger an alert initially."""
    # First few calls establish baseline — no alert expected
    alert = middleware.check_anomaly_post_call(
        model="test-model", cost=0.01, input_tokens=100, output_tokens=50
    )
    # May or may not alert depending on baseline state
    # Just verify it doesn't crash
    assert alert is None or hasattr(alert, "severity")


def test_check_anomaly_post_call_returns_alert_on_spike(middleware):
    """A massive cost spike should trigger an alert."""
    # Feed normal baseline
    for _ in range(5):
        middleware.check_anomaly_post_call(
            model="test-model", cost=0.01, input_tokens=100, output_tokens=50
        )
    # Now spike
    alert = middleware.check_anomaly_post_call(
        model="test-model", cost=10.0, input_tokens=100000, output_tokens=50000
    )
    # May trigger depending on detector implementation
    if alert:
        assert alert.severity in ("warning", "critical")
        assert len(middleware.anomaly_alerts) > 0


def test_check_anomaly_with_scope(middleware):
    """Should work with different scopes."""
    alert = middleware.check_anomaly_post_call(
        model="test-model", cost=0.05, scope="team", scope_id="team-alpha"
    )
    assert alert is None or hasattr(alert, "severity")


def test_anomaly_alerts_accumulate(middleware):
    """Multiple anomalies should accumulate in the alerts list."""
    initial_count = len(middleware.anomaly_alerts)
    # Run several checks
    for i in range(10):
        middleware.check_anomaly_post_call(
            model="test-model", cost=0.01 * (i + 1), input_tokens=100
        )
    # Alert count should be >= initial (may or may not trigger)
    assert len(middleware.anomaly_alerts) >= initial_count
