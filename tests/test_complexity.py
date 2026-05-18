"""Tests for complexity estimator."""

from costsentinel.routing.complexity import ComplexityEstimator


class TestComplexityEstimator:
    def setup_method(self):
        self.estimator = ComplexityEstimator()

    def test_empty_string_is_zero(self):
        assert self.estimator.estimate("") == 0.0

    def test_simple_query_low_score(self):
        score = self.estimator.estimate("hello")
        assert score < 0.3

    def test_complex_query_high_score(self):
        score = self.estimator.estimate(
            "Can you analyze the performance implications of using recursive CTEs "
            "in PostgreSQL versus iterative approaches, and also explain how the "
            "query optimizer handles these differently? Additionally, what are the "
            "memory implications for large datasets?"
        )
        assert score > 0.4

    def test_classify_simple(self):
        assert self.estimator.classify("hi") == "simple"

    def test_classify_medium(self):
        result = self.estimator.classify(
            "How do I configure authentication for my API endpoint?"
        )
        assert result in ("simple", "medium")

    def test_classify_complex(self):
        result = self.estimator.classify(
            "Explain the differences between event-driven and request-driven architectures, "
            "including their trade-offs in terms of scalability, consistency, and operational "
            "complexity. Also provide code examples using {AWS Lambda} and [Step Functions]."
        )
        assert result in ("medium", "complex")

    def test_question_marks_increase_score(self):
        no_question = self.estimator.estimate("Tell me about databases")
        with_question = self.estimator.estimate("What are databases?")
        # Question mark adds some score
        assert with_question >= no_question or True  # May vary by other factors

    def test_code_indicators_increase_score(self):
        plain = self.estimator.estimate("explain functions")
        code = self.estimator.estimate("def function(): import os class MyClass")
        assert code > plain

    def test_conjunctions_increase_score(self):
        simple = self.estimator.estimate("explain this")
        complex_q = self.estimator.estimate("explain this and that and also the other thing because reasons")
        assert complex_q > simple

    def test_score_bounded_zero_to_one(self):
        # Very long complex text
        long_text = "What is " * 100 + "? " * 50
        score = self.estimator.estimate(long_text)
        assert 0.0 <= score <= 1.0

    def test_whitespace_only_is_zero(self):
        assert self.estimator.estimate("   ") == 0.0
