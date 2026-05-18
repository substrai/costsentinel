"""Cost forecasting using historical spending data."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ForecastResult:
    """Result of a cost forecast."""

    method: str
    horizon_days: int
    predicted_cost: float
    daily_average: float
    confidence_low: float
    confidence_high: float
    data_points: int
    trend: str  # "increasing" | "decreasing" | "stable"


class CostForecaster:
    """Forecasts future GenAI costs based on historical spending patterns.

    Supports multiple forecasting methods:
    - linear_regression: Fits a line to daily costs
    - moving_average: Uses rolling average of recent days
    - exponential_smoothing: Weighted recent data more heavily
    """

    def __init__(self, method: str = "linear_regression"):
        """Initialize forecaster.

        Args:
            method: Forecasting method (linear_regression | moving_average | exponential_smoothing).
        """
        self.method = method

    def forecast(
        self,
        daily_costs: List[Tuple[str, float]],
        horizon_days: int = 30,
    ) -> ForecastResult:
        """Forecast future costs.

        Args:
            daily_costs: List of (date_str, cost) tuples sorted by date.
            horizon_days: Number of days to forecast.

        Returns:
            ForecastResult with predicted cost and confidence interval.
        """
        if not daily_costs:
            return ForecastResult(
                method=self.method,
                horizon_days=horizon_days,
                predicted_cost=0.0,
                daily_average=0.0,
                confidence_low=0.0,
                confidence_high=0.0,
                data_points=0,
                trend="stable",
            )

        costs = [c for _, c in daily_costs]

        if self.method == "moving_average":
            return self._moving_average(costs, horizon_days)
        elif self.method == "exponential_smoothing":
            return self._exponential_smoothing(costs, horizon_days)
        else:
            return self._linear_regression(costs, horizon_days)

    def _linear_regression(self, costs: List[float], horizon_days: int) -> ForecastResult:
        """Simple linear regression forecast."""
        n = len(costs)
        if n < 2:
            avg = costs[0] if costs else 0.0
            return ForecastResult(
                method="linear_regression",
                horizon_days=horizon_days,
                predicted_cost=avg * horizon_days,
                daily_average=avg,
                confidence_low=avg * horizon_days * 0.8,
                confidence_high=avg * horizon_days * 1.2,
                data_points=n,
                trend="stable",
            )

        # Compute linear regression: y = mx + b
        x_vals = list(range(n))
        x_mean = sum(x_vals) / n
        y_mean = sum(costs) / n

        numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_vals, costs))
        denominator = sum((x - x_mean) ** 2 for x in x_vals)

        if denominator == 0:
            slope = 0.0
        else:
            slope = numerator / denominator

        intercept = y_mean - slope * x_mean

        # Predict future daily costs
        future_costs = [slope * (n + i) + intercept for i in range(horizon_days)]
        predicted_total = sum(max(0, c) for c in future_costs)
        daily_avg = predicted_total / horizon_days if horizon_days > 0 else 0.0

        # Confidence interval (simple: ±20% based on residual variance)
        residuals = [costs[i] - (slope * i + intercept) for i in range(n)]
        variance = sum(r ** 2 for r in residuals) / max(n - 2, 1)
        std_err = variance ** 0.5

        confidence_low = max(0, predicted_total - std_err * horizon_days * 1.96)
        confidence_high = predicted_total + std_err * horizon_days * 1.96

        # Determine trend
        if slope > 0.001:
            trend = "increasing"
        elif slope < -0.001:
            trend = "decreasing"
        else:
            trend = "stable"

        return ForecastResult(
            method="linear_regression",
            horizon_days=horizon_days,
            predicted_cost=round(predicted_total, 4),
            daily_average=round(daily_avg, 4),
            confidence_low=round(confidence_low, 4),
            confidence_high=round(confidence_high, 4),
            data_points=n,
            trend=trend,
        )

    def _moving_average(self, costs: List[float], horizon_days: int) -> ForecastResult:
        """Moving average forecast using last 7 days."""
        window = min(7, len(costs))
        recent = costs[-window:]
        avg = sum(recent) / len(recent)

        predicted_total = avg * horizon_days

        # Simple confidence: ±30% for moving average
        return ForecastResult(
            method="moving_average",
            horizon_days=horizon_days,
            predicted_cost=round(predicted_total, 4),
            daily_average=round(avg, 4),
            confidence_low=round(predicted_total * 0.7, 4),
            confidence_high=round(predicted_total * 1.3, 4),
            data_points=len(costs),
            trend=self._detect_trend(costs),
        )

    def _exponential_smoothing(self, costs: List[float], horizon_days: int, alpha: float = 0.3) -> ForecastResult:
        """Exponential smoothing forecast."""
        if not costs:
            return ForecastResult(
                method="exponential_smoothing", horizon_days=horizon_days,
                predicted_cost=0.0, daily_average=0.0,
                confidence_low=0.0, confidence_high=0.0,
                data_points=0, trend="stable",
            )

        # Apply exponential smoothing
        smoothed = costs[0]
        for cost in costs[1:]:
            smoothed = alpha * cost + (1 - alpha) * smoothed

        predicted_total = smoothed * horizon_days

        return ForecastResult(
            method="exponential_smoothing",
            horizon_days=horizon_days,
            predicted_cost=round(predicted_total, 4),
            daily_average=round(smoothed, 4),
            confidence_low=round(predicted_total * 0.75, 4),
            confidence_high=round(predicted_total * 1.25, 4),
            data_points=len(costs),
            trend=self._detect_trend(costs),
        )

    def _detect_trend(self, costs: List[float]) -> str:
        """Detect trend direction from cost series."""
        if len(costs) < 3:
            return "stable"
        first_half = sum(costs[: len(costs) // 2]) / (len(costs) // 2)
        second_half = sum(costs[len(costs) // 2:]) / (len(costs) - len(costs) // 2)

        ratio = second_half / first_half if first_half > 0 else 1.0
        if ratio > 1.1:
            return "increasing"
        elif ratio < 0.9:
            return "decreasing"
        return "stable"

    def budget_vs_actual(
        self,
        daily_costs: List[Tuple[str, float]],
        daily_budget: float,
    ) -> Dict[str, Any]:
        """Compare budgeted vs actual spending.

        Args:
            daily_costs: List of (date_str, cost) tuples.
            daily_budget: Daily budget amount.

        Returns:
            Dict with variance analysis.
        """
        if not daily_costs:
            return {"days": 0, "total_budget": 0, "total_actual": 0, "variance": 0, "variance_pct": 0}

        total_actual = sum(c for _, c in daily_costs)
        total_budget = daily_budget * len(daily_costs)
        variance = total_actual - total_budget
        variance_pct = (variance / total_budget * 100) if total_budget > 0 else 0.0

        over_budget_days = sum(1 for _, c in daily_costs if c > daily_budget)

        return {
            "days": len(daily_costs),
            "total_budget": round(total_budget, 4),
            "total_actual": round(total_actual, 4),
            "variance": round(variance, 4),
            "variance_pct": round(variance_pct, 2),
            "over_budget_days": over_budget_days,
            "under_budget_days": len(daily_costs) - over_budget_days,
        }
