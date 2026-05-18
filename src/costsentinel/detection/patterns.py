"""Pattern-based anomaly detection rules."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from costsentinel.detection.anomaly import AnomalyAlert


@dataclass
class DetectionRule:
    """A configurable detection rule."""

    name: str
    condition: str  # Human-readable condition description
    severity: str  # info | warning | critical
    action: str  # alert | throttle | block


class PatternDetector:
    """Rule-based pattern detection for cost anomalies.

    Evaluates configurable rules against request metadata to detect
    suspicious patterns like off-hours premium model usage or
    repeated expensive calls.
    """

    def __init__(self, rules: Optional[List[DetectionRule]] = None):
        """Initialize pattern detector.

        Args:
            rules: List of detection rules. Uses defaults if None.
        """
        self.rules = rules or self._default_rules()
        self._triggered: List[Dict[str, Any]] = []

    def _default_rules(self) -> List[DetectionRule]:
        return [
            DetectionRule(
                name="repeated-expensive-calls",
                condition="Same endpoint > $0.10/request for 5+ consecutive calls",
                severity="warning",
                action="alert",
            ),
            DetectionRule(
                name="off-hours-premium",
                condition="Premium model used outside business hours",
                severity="info",
                action="alert",
            ),
        ]

    def check_repeated_expensive(
        self,
        endpoint: str,
        recent_costs: List[float],
        threshold: float = 0.10,
        min_consecutive: int = 5,
    ) -> Optional[AnomalyAlert]:
        """Detect repeated expensive calls to the same endpoint.

        Args:
            endpoint: The endpoint identifier.
            recent_costs: List of recent request costs (most recent last).
            threshold: Cost threshold per request.
            min_consecutive: Minimum consecutive expensive calls to trigger.

        Returns:
            AnomalyAlert if pattern detected.
        """
        if len(recent_costs) < min_consecutive:
            return None

        # Check last N calls
        tail = recent_costs[-min_consecutive:]
        if all(c > threshold for c in tail):
            avg_cost = sum(tail) / len(tail)
            alert = AnomalyAlert(
                alert_type="repeated_expensive",
                severity="warning",
                scope_key=f"endpoint:{endpoint}",
                message=f"Endpoint {endpoint}: {min_consecutive}+ consecutive calls > ${threshold:.2f} (avg ${avg_cost:.4f})",
                current_value=avg_cost,
                baseline_value=threshold,
                multiplier=avg_cost / threshold,
            )
            self._triggered.append({"rule": "repeated-expensive-calls", "alert": alert})
            return alert

        return None

    def check_off_hours_premium(
        self,
        model: str,
        hour_of_day: int,
        premium_models: Optional[List[str]] = None,
        business_hours: tuple = (8, 22),
    ) -> Optional[AnomalyAlert]:
        """Detect premium model usage outside business hours.

        Args:
            model: The model being used.
            hour_of_day: Current hour (0-23).
            premium_models: List of premium model names.
            business_hours: Tuple of (start_hour, end_hour).

        Returns:
            AnomalyAlert if off-hours premium usage detected.
        """
        premium = premium_models or ["claude-3.5-sonnet", "claude-3-opus", "gpt-4"]

        if model in premium and (hour_of_day < business_hours[0] or hour_of_day >= business_hours[1]):
            alert = AnomalyAlert(
                alert_type="off_hours_premium",
                severity="info",
                scope_key=f"model:{model}",
                message=f"Premium model {model} used at hour {hour_of_day} (outside {business_hours[0]}-{business_hours[1]})",
                current_value=float(hour_of_day),
                baseline_value=float(business_hours[0]),
                multiplier=1.0,
            )
            self._triggered.append({"rule": "off-hours-premium", "alert": alert})
            return alert

        return None

    def get_triggered_rules(self) -> List[Dict[str, Any]]:
        """Get all triggered rule events."""
        return list(self._triggered)
