"""Real-time cost streaming via CloudWatch Embedded Metrics Format (EMF).

Emits structured metrics directly to CloudWatch without custom infrastructure.
Lambda functions write EMF JSON to stdout and CloudWatch Logs automatically
extracts and stores the metrics.

Usage:
    from costsentinel.reporting.cloudwatch_emf import EMFMetricsEmitter

    emitter = EMFMetricsEmitter(namespace="SubstrAI/CostSentinel")
    emitter.emit_call_cost(
        model="claude-3-haiku",
        cost=0.0024,
        input_tokens=500,
        output_tokens=200,
        team_id="engineering",
        user_id="user-1",
    )
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class EMFMetric:
    """A single metric entry for EMF output."""

    name: str
    value: float
    unit: str = "None"  # CloudWatch unit: Count, Milliseconds, Bytes, etc.


@dataclass
class EMFDocument:
    """An EMF-formatted CloudWatch metrics document."""

    namespace: str
    metrics: List[EMFMetric]
    dimensions: Dict[str, str]
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    properties: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """Serialize to EMF JSON format for CloudWatch Logs ingestion."""
        # Build metric definitions for _aws block
        metric_definitions = [
            {"Name": m.name, "Unit": m.unit}
            for m in self.metrics
        ]

        # Build dimension set (list of dimension key names)
        dimension_keys = list(self.dimensions.keys())

        doc: Dict[str, Any] = {
            "_aws": {
                "Timestamp": self.timestamp_ms,
                "CloudWatchMetrics": [
                    {
                        "Namespace": self.namespace,
                        "Dimensions": [dimension_keys],
                        "Metrics": metric_definitions,
                    }
                ],
            }
        }

        # Add dimensions as top-level keys
        doc.update(self.dimensions)

        # Add metric values as top-level keys
        for metric in self.metrics:
            doc[metric.name] = metric.value

        # Add extra properties
        doc.update(self.properties)

        return json.dumps(doc)


class EMFMetricsEmitter:
    """Emits real-time LLM cost metrics using CloudWatch EMF.

    Writes structured JSON to stdout (or a custom stream) which
    CloudWatch Logs automatically extracts as metrics. No SDK calls
    needed — zero additional latency or infrastructure.

    Args:
        namespace: CloudWatch namespace (e.g., 'SubstrAI/CostSentinel').
        output_stream: Stream to write to (default: sys.stdout).
        enabled: Whether to emit metrics (can be disabled in dev).
        default_dimensions: Dimensions added to all metrics.
    """

    def __init__(
        self,
        namespace: str = "SubstrAI/CostSentinel",
        output_stream=None,
        enabled: bool = True,
        default_dimensions: Optional[Dict[str, str]] = None,
    ):
        self._namespace = namespace
        self._stream = output_stream or sys.stdout
        self._enabled = enabled
        self._default_dimensions = default_dimensions or {}
        self._documents_emitted: List[EMFDocument] = []

    @property
    def namespace(self) -> str:
        """The CloudWatch namespace for emitted metrics."""
        return self._namespace

    @property
    def enabled(self) -> bool:
        """Whether metric emission is active."""
        return self._enabled

    @property
    def documents_emitted(self) -> List[EMFDocument]:
        """All EMF documents emitted in this session."""
        return self._documents_emitted.copy()

    def emit_call_cost(
        self,
        model: str,
        cost: float,
        input_tokens: int,
        output_tokens: int,
        team_id: Optional[str] = None,
        user_id: Optional[str] = None,
        endpoint: Optional[str] = None,
        latency_ms: Optional[float] = None,
    ) -> Optional[str]:
        """Emit cost metrics for a single LLM API call.

        Args:
            model: Model identifier.
            cost: Actual cost in USD.
            input_tokens: Input token count.
            output_tokens: Output token count.
            team_id: Team identifier for dimension.
            user_id: User identifier for dimension.
            endpoint: API endpoint for dimension.
            latency_ms: Call latency in milliseconds.

        Returns:
            The emitted JSON string, or None if disabled.
        """
        dimensions: Dict[str, str] = {**self._default_dimensions, "Model": model}
        if team_id:
            dimensions["Team"] = team_id
        if endpoint:
            dimensions["Endpoint"] = endpoint

        metrics = [
            EMFMetric(name="CallCost", value=cost, unit="None"),
            EMFMetric(name="InputTokens", value=input_tokens, unit="Count"),
            EMFMetric(name="OutputTokens", value=output_tokens, unit="Count"),
            EMFMetric(name="TotalTokens", value=input_tokens + output_tokens, unit="Count"),
        ]

        if latency_ms is not None:
            metrics.append(EMFMetric(name="CallLatency", value=latency_ms, unit="Milliseconds"))

        properties: Dict[str, Any] = {
            "CostCents": round(cost * 100, 6),
            "CostPerToken": round(cost / (input_tokens + output_tokens), 8) if (input_tokens + output_tokens) > 0 else 0.0,
        }
        if user_id:
            properties["UserId"] = user_id

        return self._emit(metrics=metrics, dimensions=dimensions, properties=properties)

    def emit_budget_alert(
        self,
        scope: str,
        scope_id: str,
        budget_used: float,
        budget_limit: float,
        action: str,
    ) -> Optional[str]:
        """Emit a budget alert metric.

        Args:
            scope: Budget scope (global, team, user, endpoint).
            scope_id: Scope identifier.
            budget_used: Current spend.
            budget_limit: Budget ceiling.
            action: Action taken (block, downgrade, alert).

        Returns:
            Emitted JSON string.
        """
        utilization = (budget_used / budget_limit * 100) if budget_limit > 0 else 0.0
        dimensions = {
            **self._default_dimensions,
            "Scope": scope,
            "Action": action,
        }

        metrics = [
            EMFMetric(name="BudgetUtilization", value=utilization, unit="Percent"),
            EMFMetric(name="BudgetAlerts", value=1, unit="Count"),
            EMFMetric(name="BudgetUsed", value=budget_used, unit="None"),
        ]

        properties = {
            "ScopeId": scope_id,
            "BudgetLimit": budget_limit,
        }

        return self._emit(metrics=metrics, dimensions=dimensions, properties=properties)

    def emit_anomaly(
        self,
        scope: str,
        scope_id: str,
        severity: str,
        deviation_factor: float,
    ) -> Optional[str]:
        """Emit an anomaly detection metric.

        Args:
            scope: Cost scope.
            scope_id: Scope identifier.
            severity: Anomaly severity (warning, critical).
            deviation_factor: How many times above baseline.

        Returns:
            Emitted JSON string.
        """
        dimensions = {
            **self._default_dimensions,
            "Scope": scope,
            "Severity": severity,
        }

        metrics = [
            EMFMetric(name="AnomalyDetections", value=1, unit="Count"),
            EMFMetric(name="DeviationFactor", value=deviation_factor, unit="None"),
        ]

        return self._emit(
            metrics=metrics, dimensions=dimensions,
            properties={"ScopeId": scope_id},
        )

    def emit_custom(
        self,
        metric_name: str,
        value: float,
        unit: str = "None",
        dimensions: Optional[Dict[str, str]] = None,
        properties: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Emit a single custom metric.

        Args:
            metric_name: CloudWatch metric name.
            value: Metric value.
            unit: CloudWatch unit string.
            dimensions: Metric dimensions.
            properties: Extra non-metric properties to log.

        Returns:
            Emitted JSON string.
        """
        all_dimensions = {**self._default_dimensions, **(dimensions or {})}
        return self._emit(
            metrics=[EMFMetric(name=metric_name, value=value, unit=unit)],
            dimensions=all_dimensions,
            properties=properties or {},
        )

    def _emit(
        self,
        metrics: List[EMFMetric],
        dimensions: Dict[str, str],
        properties: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Write an EMF document to the output stream."""
        if not self._enabled:
            return None

        doc = EMFDocument(
            namespace=self._namespace,
            metrics=metrics,
            dimensions=dimensions,
            properties=properties or {},
        )

        json_str = doc.to_json()

        try:
            self._stream.write(json_str + "\n")
            self._stream.flush()
        except (IOError, OSError):
            pass

        self._documents_emitted.append(doc)
        return json_str
