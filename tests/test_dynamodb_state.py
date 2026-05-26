"""Tests for DynamoDB state backend."""

import pytest
import boto3
from moto import mock_aws

from costsentinel.core.dynamodb_state import DynamoDBCostState


@pytest.fixture
def dynamodb_state():
    """Create DynamoDBCostState with mocked AWS."""
    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-1")
        client.create_table(
            TableName="costsentinel-state",
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        state = DynamoDBCostState(
            table_name="costsentinel-state",
            region_name="us-east-1",
        )
        yield state


def test_increment_returns_new_total(dynamodb_state):
    """Test that increment returns the new daily total."""
    result = dynamodb_state.increment("global", "default", 5.0)
    assert result == 5.0

    result = dynamodb_state.increment("global", "default", 3.0)
    assert result == 8.0


def test_increment_different_scopes_are_independent(dynamodb_state):
    """Test that different scope_ids track independently."""
    dynamodb_state.increment("team", "alpha", 10.0)
    dynamodb_state.increment("team", "beta", 7.0)

    assert dynamodb_state.get_total("team", "alpha", "daily") == 10.0
    assert dynamodb_state.get_total("team", "beta", "daily") == 7.0


def test_get_total_returns_zero_for_missing(dynamodb_state):
    """Test that get_total returns 0.0 for non-existent entries."""
    assert dynamodb_state.get_total("global", "nonexistent", "daily") == 0.0
    assert dynamodb_state.get_total("user", "nobody", "monthly") == 0.0


def test_get_total_daily_and_monthly(dynamodb_state):
    """Test that both daily and monthly totals are tracked."""
    dynamodb_state.increment("endpoint", "api-v1", 2.5)
    dynamodb_state.increment("endpoint", "api-v1", 1.5)

    assert dynamodb_state.get_total("endpoint", "api-v1", "daily") == 4.0
    assert dynamodb_state.get_total("endpoint", "api-v1", "monthly") == 4.0


def test_get_all_totals(dynamodb_state):
    """Test get_all_totals returns all scope_ids."""
    dynamodb_state.increment("team", "alpha", 10.0)
    dynamodb_state.increment("team", "beta", 5.0)
    dynamodb_state.increment("team", "gamma", 3.0)

    totals = dynamodb_state.get_all_totals("team")
    assert "alpha" in totals
    assert "beta" in totals
    assert "gamma" in totals
    assert totals["alpha"]["daily"] == 10.0
    assert totals["beta"]["daily"] == 5.0


def test_reset_clears_scope_id(dynamodb_state):
    """Test that reset removes all records for a scope_id."""
    dynamodb_state.increment("user", "user-1", 20.0)
    assert dynamodb_state.get_total("user", "user-1", "daily") == 20.0

    dynamodb_state.reset("user", "user-1")
    assert dynamodb_state.get_total("user", "user-1", "daily") == 0.0


def test_reset_all_clears_everything(dynamodb_state):
    """Test that reset_all removes all items."""
    dynamodb_state.increment("global", "default", 100.0)
    dynamodb_state.increment("team", "alpha", 50.0)

    dynamodb_state.reset_all()

    assert dynamodb_state.get_total("global", "default", "daily") == 0.0
    assert dynamodb_state.get_total("team", "alpha", "daily") == 0.0


def test_invalid_scope_raises(dynamodb_state):
    """Test that invalid scopes raise ValueError."""
    with pytest.raises(ValueError, match="Invalid scope"):
        dynamodb_state.increment("invalid", "id", 1.0)

    with pytest.raises(ValueError, match="Invalid scope"):
        dynamodb_state.get_total("bad", "id")


def test_create_table():
    """Test create_table creates the table."""
    with mock_aws():
        state = DynamoDBCostState(
            table_name="new-table",
            region_name="us-east-1",
        )
        state.create_table(wait=False)

        # Verify table exists
        client = boto3.client("dynamodb", region_name="us-east-1")
        response = client.describe_table(TableName="new-table")
        assert response["Table"]["TableName"] == "new-table"


def test_create_table_idempotent():
    """Test create_table doesn't fail if table already exists."""
    with mock_aws():
        state = DynamoDBCostState(
            table_name="existing-table",
            region_name="us-east-1",
        )
        state.create_table(wait=False)
        # Should not raise
        state.create_table(wait=False)
