"""Tests for real-time cost streaming via CloudWatch Embedded Metrics."""

from __future__ import annotations

import io
import json
import pytest

from costsentinel.reporting.cloudwatch_emf import (
    EMFDocument,
    EMFMetric,
    EMFMetricsEmitter,
)


def _make_stream():
    """Create a StringIO stream for testing."""
    return io.StringIO()


class TestEMFDocumentFormat:
    def test_basic_structure(self):
        doc = EMFDocument(
            namespace="Test/NS",
            metrics=[EMFMetric(name="MyCost", value=0.01, unit="None")],
            dimensions={"Model": "claude-3-haiku"},
        )
        output = doc.to_json()
        data = json.loads(output)

        assert "_aws" in data
        assert data["_aws"]["CloudWatchMetrics"][0]["Namespace"] == "Test/NS"

    def test_dimensions_at_top_level(self):
        doc = EMFDocument(
            namespace="NS",
            metrics=[EMFMetric("Cost", 0.01)],
            dimensions={"Model": "haiku", "Team": "eng"},
        )
        data = json.loads(doc.to_json())
        assert data["Model"] == "haiku"
        assert data["Team"] == "eng"

    def test_metric_values_at_top_level(self):
        doc = EMFDocument(
            namespace="NS",
            metrics=[EMFMetric("CallCost", 0.0025)],
            dimensions={"Model": "haiku"},
        )
        data = json.loads(doc.to_json())
        assert data["CallCost"] == 0.0025

    def test_timestamp_present(self):
        doc = EMFDocument(
            namespace="NS",
            metrics=[EMFMetric("X", 1.0)],
            dimensions={},
        )
        data = json.loads(doc.to_json())
        assert "Timestamp" in data["_aws"]
        assert data["_aws"]["Timestamp"] > 0

    def test_metric_definitions_in_aws(self):
        doc = EMFDocument(
            namespace="NS",
            metrics=[
                EMFMetric("Cost", 0.01, "None"),
                EMFMetric("Tokens", 500, "Count"),
            ],
            dimensions={},
        )
        data = json.loads(doc.to_json())
        names = [m["Name"] for m in data["_aws"]["CloudWatchMetrics"][0]["Metrics"]]
        assert "Cost" in names
        assert "Tokens" in names

    def test_extra_properties_included(self):
        doc = EMFDocument(
            namespace="NS",
            metrics=[EMFMetric("X", 1.0)],
            dimensions={},
            properties={"UserId": "u-123", "CostCents": 0.25},
        )
        data = json.loads(doc.to_json())
        assert data["UserId"] == "u-123"
        assert data["CostCents"] == 0.25


class TestEMFEmitterCallCost:
    def test_emit_call_cost(self):
        stream = _make_stream()
        emitter = EMFMetricsEmitter(namespace="Test/CS", output_stream=stream)
        result = emitter.emit_call_cost(
            model="claude-3-haiku",
            cost=0.0024,
            input_tokens=500,
            output_tokens=200,
        )
        assert result is not None
        data = json.loads(result)
        assert data["CallCost"] == 0.0024
        assert data["InputTokens"] == 500
        assert data["OutputTokens"] == 200
        assert data["TotalTokens"] == 700
        assert data["Model"] == "claude-3-haiku"

    def test_emit_with_team_dimension(self):
        stream = _make_stream()
        emitter = EMFMetricsEmitter(output_stream=stream)
        result = emitter.emit_call_cost(
            model="haiku", cost=0.001, input_tokens=100,
            output_tokens=50, team_id="engineering",
        )
        data = json.loads(result)
        assert data["Team"] == "engineering"

    def test_emit_with_latency(self):
        stream = _make_stream()
        emitter = EMFMetricsEmitter(output_stream=stream)
        result = emitter.emit_call_cost(
            model="haiku", cost=0.001, input_tokens=100,
            output_tokens=50, latency_ms=250.5,
        )
        data = json.loads(result)
        assert data["CallLatency"] == 250.5

    def test_user_id_in_properties(self):
        stream = _make_stream()
        emitter = EMFMetricsEmitter(output_stream=stream)
        result = emitter.emit_call_cost(
            model="haiku", cost=0.001, input_tokens=100,
            output_tokens=50, user_id="user-42",
        )
        data = json.loads(result)
        assert data["UserId"] == "user-42"

    def test_disabled_emitter_returns_none(self):
        emitter = EMFMetricsEmitter(enabled=False)
        result = emitter.emit_call_cost(
            model="haiku", cost=0.001, input_tokens=100, output_tokens=50,
        )
        assert result is None


class TestEMFEmitterBudgetAlert:
    def test_emit_budget_alert(self):
        stream = _make_stream()
        emitter = EMFMetricsEmitter(output_stream=stream)
        result = emitter.emit_budget_alert(
            scope="team", scope_id="engineering",
            budget_used=22.5, budget_limit=25.0, action="alert",
        )
        data = json.loads(result)
        assert data["BudgetUtilization"] == 90.0
        assert data["BudgetAlerts"] == 1
        assert data["Scope"] == "team"
        assert data["Action"] == "alert"

    def test_budget_utilization_calculation(self):
        stream = _make_stream()
        emitter = EMFMetricsEmitter(output_stream=stream)
        result = emitter.emit_budget_alert(
            scope="user", scope_id="u1",
            budget_used=4.0, budget_limit=5.0, action="block",
        )
        data = json.loads(result)
        assert data["BudgetUtilization"] == 80.0


class TestEMFEmitterAnomaly:
    def test_emit_anomaly(self):
        stream = _make_stream()
        emitter = EMFMetricsEmitter(output_stream=stream)
        result = emitter.emit_anomaly(
            scope="global", scope_id="default",
            severity="critical", deviation_factor=5.2,
        )
        data = json.loads(result)
        assert data["AnomalyDetections"] == 1
        assert data["DeviationFactor"] == 5.2
        assert data["Severity"] == "critical"


class TestEMFEmitterCustom:
    def test_emit_custom_metric(self):
        stream = _make_stream()
        emitter = EMFMetricsEmitter(output_stream=stream)
        result = emitter.emit_custom(
            metric_name="RequestCount",
            value=42.0,
            unit="Count",
            dimensions={"Service": "chat"},
        )
        data = json.loads(result)
        assert data["RequestCount"] == 42.0
        assert data["Service"] == "chat"


class TestDefaultDimensions:
    def test_default_dimensions_added(self):
        stream = _make_stream()
        emitter = EMFMetricsEmitter(
            output_stream=stream,
            default_dimensions={"Environment": "prod", "Region": "us-east-1"},
        )
        result = emitter.emit_custom("X", 1.0)
        data = json.loads(result)
        assert data["Environment"] == "prod"
        assert data["Region"] == "us-east-1"


class TestDocumentTracking:
    def test_documents_tracked(self):
        stream = _make_stream()
        emitter = EMFMetricsEmitter(output_stream=stream)
        emitter.emit_call_cost("m", 0.001, 100, 50)
        emitter.emit_call_cost("m", 0.002, 200, 100)
        assert len(emitter.documents_emitted) == 2

    def test_documents_is_copy(self):
        stream = _make_stream()
        emitter = EMFMetricsEmitter(output_stream=stream)
        emitter.emit_call_cost("m", 0.001, 100, 50)
        docs = emitter.documents_emitted
        docs.clear()
        assert len(emitter.documents_emitted) == 1

    def test_disabled_no_documents(self):
        emitter = EMFMetricsEmitter(enabled=False)
        emitter.emit_call_cost("m", 0.001, 100, 50)
        assert len(emitter.documents_emitted) == 0


class TestStreamOutput:
    def test_written_to_stream(self):
        stream = _make_stream()
        emitter = EMFMetricsEmitter(output_stream=stream)
        emitter.emit_call_cost("haiku", 0.001, 100, 50)
        content = stream.getvalue()
        assert len(content) > 0
        assert "_aws" in content

    def test_each_emit_on_new_line(self):
        stream = _make_stream()
        emitter = EMFMetricsEmitter(output_stream=stream)
        emitter.emit_call_cost("haiku", 0.001, 100, 50)
        emitter.emit_call_cost("haiku", 0.002, 200, 100)
        lines = [l for l in stream.getvalue().strip().split("\n") if l]
        assert len(lines) == 2
        for line in lines:
            json.loads(line)  # Each line must be valid JSON
