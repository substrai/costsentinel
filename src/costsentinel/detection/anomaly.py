"""Anomaly detection engine using statistical methods."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from costsentinel.detection.baseline import BaselineLearner, BaselineMetrics


@dataclass
class AnomalyAlert:
    """An anomaly detection alert."""

    alert_type: str  # cost_spike | runaway_session | high_token_ratio | unusual_pattern
    severity: str  # info | warning | critical
    scope_key: str
    message: str
    current_value: float
    baseline_value: float
    multiplier: float
    timestamp: float = field(default_factory=time.time)


class AnomalyDetector:
    """Detects unusual spending patterns using statistical analysis.

    Compares current spending rates against learned baselines using
    z-score analysis and configurable multiplier thresholds.
    """

    def __init__(
        self,
        baseline_learner: BaselineLearner,
        spike_multiplier: float = 3.0,
        warning_multiplier: float = 2.0,
    ):
        """Initialize anomaly detector.

        Args:
            baseline_learner: BaselineLearner instance with historical data.
            spike_multiplier: Multiplier for critical spike detection (default 3x baseline).
            warning_multiplier: Multiplier for warning detection (default 2x baseline).
        """
        self.baseline_learner = baseline_learner
        self.spike_multiplier = spike_multiplier
        self.warning_multiplier = warning_multiplier
        self._alerts: List[AnomalyAlert] = []

    def check_cost_rate(self, scope_key: str, current_hourly_cost: float) -> Optional[AnomalyAlert]:
        """Check if current cost rate is anomalous.

        Args:
            scope_key: The scope identifier.
            current_hourly_cost: Current cost rate per hour.

        Returns:
            AnomalyAlert if anomaly detected, None otherwise.
        """
        baseline = self.baseline_learner.get_baseline(scope_key)
        if not baseline or baseline.sample_count < 10:
            return None

        if baseline.mean_cost_per_hour <= 0:
            return None

        multiplier = current_hourly_cost / baseline.mean_cost_per_hour

        if multiplier >= self.spike_multiplier:
            alert = AnomalyAlert(
                alert_type="cost_spike",
                severity="critical",
                scope_key=scope_key,
                message=f"Cost rate {multiplier:.1f}x above baseline for {scope_key}",
                current_value=current_hourly_cost,
                baseline_value=baseline.mean_cost_per_hour,
                multiplier=multiplier,
            )
            self._alerts.append(alert)
            return alert

        if multiplier >= self.warning_multiplier:
            alert = AnomalyAlert(
                alert_type="cost_spike",
                severity="warning",
                scope_key=scope_key,
                message=f"Cost rate {multiplier:.1f}x above baseline for {scope_key}",
                current_value=current_hourly_cost,
                baseline_value=baseline.mean_cost_per_hour,
                multiplier=multiplier,
            )
            self._alerts.append(alert)
            return alert

        return None

    def check_token_ratio(
        self, scope_key: str, input_tokens: int, output_tokens: int
    ) -> Optional[AnomalyAlert]:
        """Detect potential prompt injection (output >> input).

        Args:
            scope_key: The scope identifier.
            input_tokens: Number of input tokens.
            output_tokens: Number of output tokens.

        Returns:
            AnomalyAlert if suspicious ratio detected.
        """
        if input_tokens <= 0:
            return None

        ratio = output_tokens / input_tokens

        # Suspicious if output is 10x+ the input (possible prompt injection)
        if ratio >= 10.0:
            alert = AnomalyAlert(
                alert_type="high_token_ratio",
                severity="critical",
                scope_key=scope_key,
                message=f"Output/input token ratio {ratio:.1f}x for {scope_key} (possible prompt injection)",
                current_value=ratio,
                baseline_value=1.0,
                multiplier=ratio,
            )
            self._alerts.append(alert)
            return alert

        if ratio >= 5.0:
            alert = AnomalyAlert(
                alert_type="high_token_ratio",
                severity="warning",
                scope_key=scope_key,
                message=f"High output/input ratio {ratio:.1f}x for {scope_key}",
                current_value=ratio,
                baseline_value=1.0,
                multiplier=ratio,
            )
            self._alerts.append(alert)
            return alert

        return None

    def check_session_runaway(
        self, session_id: str, session_cost: float, session_duration_seconds: float
    ) -> Optional[AnomalyAlert]:
        """Detect runaway agent sessions.

        Args:
            session_id: The session identifier.
            session_cost: Total session cost so far.
            session_duration_seconds: Session duration in seconds.

        Returns:
            AnomalyAlert if runaway session detected.
        """
        if session_cost >= 2.0 and session_duration_seconds >= 300:
            alert = AnomalyAlert(
                alert_type="runaway_session",
                severity="warning",
                scope_key=f"session:{session_id}",
                message=f"Runaway session {session_id}: ${session_cost:.2f} over {session_duration_seconds:.0f}s",
                current_value=session_cost,
                baseline_value=2.0,
                multiplier=session_cost / 2.0,
            )
            self._alerts.append(alert)
            return alert

        return None

    def get_recent_alerts(self, last_n: int = 50) -> List[AnomalyAlert]:
        """Get recent anomaly alerts.

        Args:
            last_n: Number of recent alerts to return.

        Returns:
            List of recent AnomalyAlert objects.
        """
        return self._alerts[-last_n:]

    def get_alerts_by_severity(self, severity: str) -> List[AnomalyAlert]:
        """Get alerts filtered by severity.

        Args:
            severity: "info", "warning", or "critical".

        Returns:
            List of matching alerts.
        """
        return [a for a in self._alerts if a.severity == severity]
