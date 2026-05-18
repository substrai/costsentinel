"""Tests for baseline learner."""

import tempfile
from pathlib import Path

from costsentinel.detection.baseline import BaselineLearner


class TestBaselineLearner:
    def setup_method(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self.learner = BaselineLearner(window_days=7, storage_path=self.tmp.name)

    def teardown_method(self):
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_no_baseline_initially(self):
        assert self.learner.get_baseline("user:test") is None

    def test_has_baseline_false_with_few_samples(self):
        for i in range(5):
            self.learner.record("user:test", cost=0.01, tokens=100)
        assert self.learner.has_baseline("user:test") is False

    def test_has_baseline_true_with_enough_samples(self):
        for i in range(15):
            self.learner.record("user:test", cost=0.01, tokens=100)
        assert self.learner.has_baseline("user:test") is True

    def test_baseline_metrics_computed(self):
        for i in range(12):
            self.learner.record("scope:a", cost=0.05, tokens=200)
        baseline = self.learner.get_baseline("scope:a")
        assert baseline is not None
        assert baseline.sample_count == 12
        assert baseline.mean_tokens_per_request > 0

    def test_different_scopes_independent(self):
        for i in range(12):
            self.learner.record("scope:x", cost=0.01, tokens=50)
        self.learner.record("scope:y", cost=0.10, tokens=500)
        assert self.learner.has_baseline("scope:x") is True
        assert self.learner.has_baseline("scope:y") is False

    def test_refresh_recomputes(self):
        for i in range(12):
            self.learner.record("scope:r", cost=0.02, tokens=100)
        self.learner.refresh()
        baseline = self.learner.get_baseline("scope:r")
        assert baseline is not None

    def test_persistence(self):
        for i in range(12):
            self.learner.record("scope:p", cost=0.03, tokens=150)
        learner2 = BaselineLearner(storage_path=self.tmp.name)
        assert learner2.has_baseline("scope:p") is True
