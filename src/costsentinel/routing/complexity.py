"""Query complexity estimation for routing decisions."""

from __future__ import annotations

import re


class ComplexityEstimator:
    """Estimates query complexity for model routing decisions.

    Uses heuristics based on word count, question markers, special characters,
    word length, and nested clause indicators to score complexity 0.0-1.0.
    """

    def estimate(self, text: str) -> float:
        """Estimate complexity of a query on a 0.0-1.0 scale.

        Args:
            text: The query text to analyze.

        Returns:
            Complexity score between 0.0 and 1.0.
        """
        if not text or not text.strip():
            return 0.0

        words = text.split()
        word_count = len(words)

        # Factor 1: Word count (longer = more complex)
        word_count_score = min(word_count / 30.0, 1.0) * 0.25

        # Factor 2: Question complexity
        question_score = 0.0
        if "?" in text:
            question_score = 0.1
            # Multi-part questions are more complex
            question_score += min(text.count("?") - 1, 2) * 0.05

        # Factor 3: Special characters / technical content
        special_chars = sum(1 for c in text if not c.isalnum() and not c.isspace())
        special_ratio = special_chars / max(len(text), 1)
        special_score = min(special_ratio * 5, 1.0) * 0.15

        # Factor 4: Average word length (technical terms are longer)
        avg_word_len = sum(len(w) for w in words) / max(word_count, 1)
        word_len_score = min(avg_word_len / 10.0, 1.0) * 0.2

        # Factor 5: Nested clauses / conjunctions
        conjunctions = len(re.findall(r"\b(and|or|but|however|therefore|because|although|while)\b", text.lower()))
        clause_score = min(conjunctions / 4.0, 1.0) * 0.15

        # Factor 6: Code/technical indicators
        code_indicators = len(re.findall(r"[{}\[\]<>|`]|def |class |import |function ", text))
        code_score = min(code_indicators / 3.0, 1.0) * 0.15

        total = word_count_score + question_score + special_score + word_len_score + clause_score + code_score
        return max(0.0, min(1.0, total))

    def classify(self, text: str) -> str:
        """Classify query complexity level.

        Args:
            text: The query text to classify.

        Returns:
            "simple", "medium", or "complex".
        """
        score = self.estimate(text)
        if score < 0.3:
            return "simple"
        if score < 0.6:
            return "medium"
        return "complex"
