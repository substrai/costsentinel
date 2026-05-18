"""Tests for cost optimizer."""

from costsentinel.reporting.optimizer import CostOptimizer, OptimizationSuggestion


class TestCostOptimizer:
    def setup_method(self):
        self.optimizer = CostOptimizer()

    def test_empty_data_no_suggestions(self):
        suggestions = self.optimizer.analyze([])
        assert len(suggestions) == 0

    def test_model_downgrade_suggestion(self):
        # 50% simple queries
        data = [{"complexity": 0.1, "model": "sonnet", "tokens": 100}] * 5
        data += [{"complexity": 0.8, "model": "sonnet", "tokens": 500}] * 5
        suggestions = self.optimizer.analyze(data)
        model_suggestions = [s for s in suggestions if s.category == "model_routing"]
        assert len(model_suggestions) == 1

    def test_no_model_downgrade_when_all_complex(self):
        data = [{"complexity": 0.8, "model": "sonnet", "tokens": 500}] * 10
        suggestions = self.optimizer.analyze(data)
        model_suggestions = [s for s in suggestions if s.category == "model_routing"]
        assert len(model_suggestions) == 0

    def test_token_waste_suggestion(self):
        # High output/input ratio
        data = [{"input_tokens": 100, "output_tokens": 500, "complexity": 0.5}] * 5
        data += [{"input_tokens": 100, "output_tokens": 50, "complexity": 0.5}] * 5
        suggestions = self.optimizer.analyze(data)
        token_suggestions = [s for s in suggestions if s.category == "token_reduction"]
        assert len(token_suggestions) == 1

    def test_caching_suggestion(self):
        # Many duplicate queries
        data = [{"query": "what is AI?", "complexity": 0.3}] * 8
        data += [{"query": "unique query " + str(i), "complexity": 0.5} for i in range(2)]
        suggestions = self.optimizer.analyze(data)
        cache_suggestions = [s for s in suggestions if s.category == "caching"]
        assert len(cache_suggestions) == 1

    def test_no_caching_when_unique(self):
        data = [{"query": f"unique query {i}", "complexity": 0.5} for i in range(20)]
        suggestions = self.optimizer.analyze(data)
        cache_suggestions = [s for s in suggestions if s.category == "caching"]
        assert len(cache_suggestions) == 0

    def test_suggestions_sorted_by_savings(self):
        # Create data that triggers multiple suggestions
        data = [{"complexity": 0.1, "query": "same", "input_tokens": 50, "output_tokens": 200}] * 10
        suggestions = self.optimizer.analyze(data)
        if len(suggestions) >= 2:
            assert suggestions[0].estimated_savings_pct >= suggestions[1].estimated_savings_pct

    def test_suggestion_has_action(self):
        data = [{"complexity": 0.1, "model": "sonnet", "tokens": 100}] * 10
        suggestions = self.optimizer.analyze(data)
        for s in suggestions:
            assert s.action != ""
            assert s.priority in ("high", "medium", "low")

    def test_suggestion_has_category(self):
        data = [{"complexity": 0.1, "query": "same", "model": "sonnet"}] * 10
        suggestions = self.optimizer.analyze(data)
        valid_categories = {"model_routing", "token_reduction", "caching", "scheduling"}
        for s in suggestions:
            assert s.category in valid_categories
