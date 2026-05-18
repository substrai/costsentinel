"""Tests for cost forecasting."""

from costsentinel.reporting.forecast import CostForecaster, ForecastResult


class TestCostForecaster:
    def setup_method(self):
        self.forecaster = CostForecaster(method="linear_regression")

    def test_empty_data(self):
        result = self.forecaster.forecast([], horizon_days=30)
        assert result.predicted_cost == 0.0
        assert result.data_points == 0

    def test_single_day(self):
        result = self.forecaster.forecast([("2025-01-01", 10.0)], horizon_days=30)
        assert result.predicted_cost > 0
        assert result.daily_average > 0

    def test_linear_increasing(self):
        daily = [(f"2025-01-{i+1:02d}", float(i)) for i in range(1, 15)]
        result = self.forecaster.forecast(daily, horizon_days=30)
        assert result.trend == "increasing"
        assert result.predicted_cost > 0

    def test_linear_stable(self):
        daily = [(f"2025-01-{i+1:02d}", 5.0) for i in range(14)]
        result = self.forecaster.forecast(daily, horizon_days=30)
        assert result.trend == "stable"
        assert abs(result.daily_average - 5.0) < 1.0

    def test_moving_average_method(self):
        forecaster = CostForecaster(method="moving_average")
        daily = [(f"2025-01-{i+1:02d}", 3.0) for i in range(10)]
        result = forecaster.forecast(daily, horizon_days=30)
        assert result.method == "moving_average"
        assert abs(result.daily_average - 3.0) < 0.5

    def test_exponential_smoothing_method(self):
        forecaster = CostForecaster(method="exponential_smoothing")
        daily = [(f"2025-01-{i+1:02d}", 2.0) for i in range(10)]
        result = forecaster.forecast(daily, horizon_days=30)
        assert result.method == "exponential_smoothing"
        assert result.predicted_cost > 0

    def test_confidence_interval(self):
        daily = [(f"2025-01-{i+1:02d}", float(i % 5 + 1)) for i in range(14)]
        result = self.forecaster.forecast(daily, horizon_days=30)
        assert result.confidence_low <= result.predicted_cost
        assert result.confidence_high >= result.predicted_cost

    def test_horizon_affects_total(self):
        daily = [(f"2025-01-{i+1:02d}", 5.0) for i in range(14)]
        result_7 = self.forecaster.forecast(daily, horizon_days=7)
        result_30 = self.forecaster.forecast(daily, horizon_days=30)
        assert result_30.predicted_cost > result_7.predicted_cost

    def test_budget_vs_actual_under(self):
        daily = [(f"2025-01-{i+1:02d}", 3.0) for i in range(10)]
        result = self.forecaster.budget_vs_actual(daily, daily_budget=5.0)
        assert result["variance"] < 0  # Under budget
        assert result["over_budget_days"] == 0

    def test_budget_vs_actual_over(self):
        daily = [(f"2025-01-{i+1:02d}", 8.0) for i in range(10)]
        result = self.forecaster.budget_vs_actual(daily, daily_budget=5.0)
        assert result["variance"] > 0  # Over budget
        assert result["over_budget_days"] == 10

    def test_budget_vs_actual_empty(self):
        result = self.forecaster.budget_vs_actual([], daily_budget=5.0)
        assert result["days"] == 0

    def test_decreasing_trend(self):
        daily = [(f"2025-01-{i+1:02d}", 20.0 - float(i)) for i in range(14)]
        result = self.forecaster.forecast(daily, horizon_days=30)
        assert result.trend == "decreasing"
