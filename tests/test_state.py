"""Tests for state management."""

import json
import os
import tempfile

import pytest

from costsentinel.core.state import CostState, _get_period_key


class TestCostState:
    """Test suite for CostState."""

    @pytest.fixture
    def state(self, tmp_path):
        """Create a CostState with a temporary file."""
        state_file = str(tmp_path / "test_state.json")
        return CostState(state_file)

    def test_initial_state_empty(self, state):
        assert state.get_total("global", "default", "daily") == 0.0
        assert state.get_total("global", "default", "monthly") == 0.0

    def test_increment_daily(self, state):
        result = state.increment("global", "default", 1.50)
        assert result == 1.50
        assert state.get_total("global", "default", "daily") == 1.50

    def test_increment_accumulates(self, state):
        state.increment("global", "default", 1.00)
        state.increment("global", "default", 2.00)
        state.increment("global", "default", 0.50)
        assert state.get_total("global", "default", "daily") == 3.50

    def test_increment_updates_monthly(self, state):
        state.increment("global", "default", 5.00)
        assert state.get_total("global", "default", "monthly") == 5.00

    def test_multiple_scopes(self, state):
        state.increment("global", "default", 10.0)
        state.increment("team", "team-alpha", 3.0)
        state.increment("team", "team-beta", 7.0)
        state.increment("user", "user-1", 2.0)

        assert state.get_total("global", "default", "daily") == 10.0
        assert state.get_total("team", "team-alpha", "daily") == 3.0
        assert state.get_total("team", "team-beta", "daily") == 7.0
        assert state.get_total("user", "user-1", "daily") == 2.0

    def test_get_all_totals(self, state):
        state.increment("team", "team-alpha", 3.0)
        state.increment("team", "team-beta", 7.0)

        totals = state.get_all_totals("team")
        assert "team-alpha" in totals
        assert "team-beta" in totals
        assert totals["team-alpha"]["daily"] == 3.0
        assert totals["team-beta"]["daily"] == 7.0

    def test_get_all_totals_empty_scope(self, state):
        totals = state.get_all_totals("endpoint")
        assert totals == {}

    def test_reset(self, state):
        state.increment("user", "user-1", 5.0)
        assert state.get_total("user", "user-1", "daily") == 5.0

        state.reset("user", "user-1")
        assert state.get_total("user", "user-1", "daily") == 0.0
        assert state.get_total("user", "user-1", "monthly") == 0.0

    def test_reset_nonexistent(self, state):
        # Should not raise
        state.reset("user", "nonexistent")

    def test_reset_all(self, state):
        state.increment("global", "default", 10.0)
        state.increment("team", "team-alpha", 5.0)
        state.reset_all()

        assert state.get_total("global", "default", "daily") == 0.0
        assert state.get_total("team", "team-alpha", "daily") == 0.0

    def test_invalid_scope_raises(self, state):
        with pytest.raises(ValueError, match="Invalid scope"):
            state.increment("invalid", "id", 1.0)

        with pytest.raises(ValueError, match="Invalid scope"):
            state.get_total("invalid", "id")

    def test_persistence(self, tmp_path):
        state_file = str(tmp_path / "persist_state.json")

        # Write with one instance
        state1 = CostState(state_file)
        state1.increment("global", "default", 42.0)

        # Read with another instance
        state2 = CostState(state_file)
        assert state2.get_total("global", "default", "daily") == 42.0

    def test_period_key_daily(self):
        key = _get_period_key("daily")
        # Should be YYYY-MM-DD format
        assert len(key) == 10
        assert key[4] == "-"
        assert key[7] == "-"

    def test_period_key_monthly(self):
        key = _get_period_key("monthly")
        # Should be YYYY-MM format
        assert len(key) == 7
        assert key[4] == "-"

    def test_invalid_period_raises(self):
        with pytest.raises(ValueError, match="Invalid period"):
            _get_period_key("weekly")
