"""Tests for cost attribution."""

from datetime import datetime, timezone

import pytest

from costsentinel.policies.attribution import AttributionStore, CostAttribution


class TestCostAttribution:
    """Test suite for CostAttribution and AttributionStore."""

    @pytest.fixture
    def store(self, tmp_path):
        """Create an AttributionStore with a temporary file."""
        return AttributionStore(str(tmp_path / "test_attr.json"))

    @pytest.fixture
    def sample_attribution(self):
        """Create a sample attribution record."""
        return CostAttribution(
            user_id="user-1",
            team_id="team-alpha",
            endpoint="/api/chat",
            model="claude-3-haiku",
            timestamp=datetime.now(timezone.utc).isoformat(),
            cost=0.005,
            tokens_in=1000,
            tokens_out=500,
        )

    def test_record_attribution(self, store, sample_attribution):
        store.record(sample_attribution)
        records = store.get_by_user("user-1", "daily")
        assert len(records) == 1
        assert records[0].user_id == "user-1"
        assert records[0].cost == 0.005

    def test_record_multiple(self, store):
        for i in range(5):
            attr = CostAttribution(
                user_id=f"user-{i % 2}",
                team_id="team-alpha",
                endpoint="/api/chat",
                model="claude-3-haiku",
                timestamp=datetime.now(timezone.utc).isoformat(),
                cost=0.001 * (i + 1),
                tokens_in=100 * (i + 1),
                tokens_out=50 * (i + 1),
            )
            store.record(attr)

        user_0_records = store.get_by_user("user-0", "daily")
        user_1_records = store.get_by_user("user-1", "daily")
        assert len(user_0_records) == 3  # indices 0, 2, 4
        assert len(user_1_records) == 2  # indices 1, 3

    def test_get_by_team(self, store):
        for team in ["team-a", "team-a", "team-b"]:
            attr = CostAttribution(
                user_id="user-1",
                team_id=team,
                endpoint="/api/chat",
                model="claude-3-haiku",
                timestamp=datetime.now(timezone.utc).isoformat(),
                cost=0.01,
                tokens_in=500,
                tokens_out=200,
            )
            store.record(attr)

        team_a = store.get_by_team("team-a", "daily")
        team_b = store.get_by_team("team-b", "daily")
        assert len(team_a) == 2
        assert len(team_b) == 1

    def test_get_by_endpoint(self, store):
        for ep in ["/api/chat", "/api/chat", "/api/summarize"]:
            attr = CostAttribution(
                user_id="user-1",
                team_id="team-a",
                endpoint=ep,
                model="claude-3-haiku",
                timestamp=datetime.now(timezone.utc).isoformat(),
                cost=0.01,
                tokens_in=500,
                tokens_out=200,
            )
            store.record(attr)

        chat = store.get_by_endpoint("/api/chat", "daily")
        summarize = store.get_by_endpoint("/api/summarize", "daily")
        assert len(chat) == 2
        assert len(summarize) == 1

    def test_get_summary(self, store):
        models = ["claude-3-haiku", "claude-3.5-sonnet", "claude-3-haiku"]
        for i, model in enumerate(models):
            attr = CostAttribution(
                user_id="user-1",
                team_id="team-a",
                endpoint="/api/chat",
                model=model,
                timestamp=datetime.now(timezone.utc).isoformat(),
                cost=0.01 * (i + 1),
                tokens_in=100 * (i + 1),
                tokens_out=50 * (i + 1),
            )
            store.record(attr)

        summary = store.get_summary("daily")
        assert summary["total_calls"] == 3
        assert summary["total_cost"] == pytest.approx(0.06, abs=1e-6)
        assert "claude-3-haiku" in summary["by_model"]
        assert "claude-3.5-sonnet" in summary["by_model"]
        assert summary["by_model"]["claude-3-haiku"]["calls"] == 2

    def test_get_summary_empty(self, store):
        summary = store.get_summary("daily")
        assert summary["total_calls"] == 0
        assert summary["total_cost"] == 0.0

    def test_clear(self, store, sample_attribution):
        store.record(sample_attribution)
        store.clear()
        records = store.get_by_user("user-1", "daily")
        assert len(records) == 0

    def test_attribution_dataclass(self):
        attr = CostAttribution(
            user_id="u1",
            team_id="t1",
            endpoint="/ep",
            model="model",
            timestamp="2024-01-15T10:00:00+00:00",
            cost=0.5,
            tokens_in=1000,
            tokens_out=500,
        )
        assert attr.user_id == "u1"
        assert attr.cost == 0.5
