"""DynamoDB state backend for production cost tracking.

Provides the same interface as CostState but uses DynamoDB for
durable, concurrent-safe storage with atomic counters. Suitable
for multi-Lambda deployments where file-based state is not viable.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

try:
    import boto3
    from botocore.config import Config as BotocoreConfig
    from botocore.exceptions import ClientError
except ImportError as e:
    raise ImportError(
        "boto3 is required for DynamoDB state backend. "
        "Install with: pip install substrai-costsentinel[aws]"
    ) from e


def _get_period_key(period: str) -> str:
    """Get the current period key for bucketing costs."""
    now = datetime.now(timezone.utc)
    if period == "daily":
        return now.strftime("%Y-%m-%d")
    elif period == "monthly":
        return now.strftime("%Y-%m")
    else:
        raise ValueError(f"Invalid period '{period}'. Must be 'daily' or 'monthly'.")


class DynamoDBCostState:
    """DynamoDB-backed cost state with atomic increment operations.

    Uses a single DynamoDB table with composite keys:
      - PK: "{scope}#{scope_id}"
      - SK: "{period}#{period_key}"

    Attributes are stored as:
      - amount: Decimal cost total (uses ADD for atomic increment)
      - ttl: Unix timestamp for automatic item expiration

    Table schema:
        PK (String) | SK (String) | amount (Number) | ttl (Number)
        global#default | daily#2024-01-15 | 12.50 | 1705449600
        team#alpha | monthly#2024-01 | 150.00 | 1706745600
    """

    VALID_SCOPES = ("global", "team", "endpoint", "user")

    # Default TTL: 90 days for daily records, 365 days for monthly
    TTL_DAYS = {"daily": 90, "monthly": 365}

    def __init__(
        self,
        table_name: str = "costsentinel-state",
        region_name: Optional[str] = None,
        boto_session: Optional[Any] = None,
        endpoint_url: Optional[str] = None,
    ):
        """Initialize DynamoDB state backend.

        Args:
            table_name: DynamoDB table name.
            region_name: AWS region. Defaults to boto3 default.
            boto_session: Optional pre-configured boto3 session.
            endpoint_url: Optional endpoint URL (for LocalStack/testing).
        """
        self._table_name = table_name
        self._lock = threading.Lock()

        session = boto_session or boto3.Session(region_name=region_name)
        client_kwargs: Dict[str, Any] = {
            "service_name": "dynamodb",
            "config": BotocoreConfig(
                user_agent_extra="costsentinel",
                retries={"max_attempts": 3, "mode": "adaptive"},
            ),
        }
        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url

        self._client = session.client(**client_kwargs)
        self._table_name = table_name

    @property
    def table_name(self) -> str:
        """DynamoDB table name."""
        return self._table_name

    def _make_pk(self, scope: str, scope_id: str) -> str:
        """Build partition key."""
        return f"{scope}#{scope_id}"

    def _make_sk(self, period: str, period_key: str) -> str:
        """Build sort key."""
        return f"{period}#{period_key}"

    def _compute_ttl(self, period: str) -> int:
        """Compute TTL timestamp for item expiration."""
        import time

        ttl_days = self.TTL_DAYS.get(period, 90)
        return int(time.time()) + (ttl_days * 86400)

    def _validate_scope(self, scope: str) -> None:
        """Validate scope value."""
        if scope not in self.VALID_SCOPES:
            raise ValueError(
                f"Invalid scope '{scope}'. Must be one of {self.VALID_SCOPES}."
            )

    def increment(self, scope: str, scope_id: str, amount: float) -> float:
        """Atomically increment cost total for a scope.

        Uses DynamoDB's ADD operation for concurrent-safe increments
        without read-modify-write race conditions.

        Args:
            scope: One of "global", "team", "endpoint", "user".
            scope_id: Identifier within the scope.
            amount: Cost amount to add (USD).

        Returns:
            New total for the current daily period.
        """
        self._validate_scope(scope)

        from decimal import Decimal

        pk = self._make_pk(scope, scope_id)
        daily_key = _get_period_key("daily")
        monthly_key = _get_period_key("monthly")

        # Atomic increment for daily
        daily_response = self._client.update_item(
            TableName=self._table_name,
            Key={
                "PK": {"S": pk},
                "SK": {"S": self._make_sk("daily", daily_key)},
            },
            UpdateExpression="ADD amount :amt SET #ttl = if_not_exists(#ttl, :ttl)",
            ExpressionAttributeNames={"#ttl": "ttl"},
            ExpressionAttributeValues={
                ":amt": {"N": str(Decimal(str(amount)))},
                ":ttl": {"N": str(self._compute_ttl("daily"))},
            },
            ReturnValues="UPDATED_NEW",
        )

        # Atomic increment for monthly
        self._client.update_item(
            TableName=self._table_name,
            Key={
                "PK": {"S": pk},
                "SK": {"S": self._make_sk("monthly", monthly_key)},
            },
            UpdateExpression="ADD amount :amt SET #ttl = if_not_exists(#ttl, :ttl)",
            ExpressionAttributeNames={"#ttl": "ttl"},
            ExpressionAttributeValues={
                ":amt": {"N": str(Decimal(str(amount)))},
                ":ttl": {"N": str(self._compute_ttl("monthly"))},
            },
            ReturnValues="NONE",
        )

        # Return new daily total
        new_amount = daily_response["Attributes"]["amount"]["N"]
        return float(new_amount)

    def get_total(
        self, scope: str, scope_id: str, period: str = "daily"
    ) -> float:
        """Get the current cost total for a scope.

        Args:
            scope: One of "global", "team", "endpoint", "user".
            scope_id: Identifier within the scope.
            period: "daily" or "monthly".

        Returns:
            Current total for the specified period, or 0.0 if no data.
        """
        self._validate_scope(scope)

        pk = self._make_pk(scope, scope_id)
        period_key = _get_period_key(period)
        sk = self._make_sk(period, period_key)

        try:
            response = self._client.get_item(
                TableName=self._table_name,
                Key={"PK": {"S": pk}, "SK": {"S": sk}},
                ProjectionExpression="amount",
            )
        except ClientError:
            return 0.0

        item = response.get("Item")
        if not item or "amount" not in item:
            return 0.0

        return float(item["amount"]["N"])

    def get_all_totals(self, scope: str) -> Dict[str, Dict[str, float]]:
        """Get all totals for a scope using a query on the PK prefix.

        Args:
            scope: One of "global", "team", "endpoint", "user".

        Returns:
            Dict mapping scope_ids to {"daily": amount, "monthly": amount}.
        """
        self._validate_scope(scope)

        daily_key = _get_period_key("daily")
        monthly_key = _get_period_key("monthly")

        # Scan with filter for the scope prefix
        # Note: For production with many items, consider a GSI
        response = self._client.scan(
            TableName=self._table_name,
            FilterExpression="begins_with(PK, :prefix)",
            ExpressionAttributeValues={":prefix": {"S": f"{scope}#"}},
        )

        result: Dict[str, Dict[str, float]] = {}

        for item in response.get("Items", []):
            pk = item["PK"]["S"]
            sk = item["SK"]["S"]
            amount = float(item.get("amount", {}).get("N", "0"))

            # Extract scope_id from PK
            scope_id = pk.split("#", 1)[1]

            if scope_id not in result:
                result[scope_id] = {"daily": 0.0, "monthly": 0.0}

            # Match current period keys
            if sk == f"daily#{daily_key}":
                result[scope_id]["daily"] = amount
            elif sk == f"monthly#{monthly_key}":
                result[scope_id]["monthly"] = amount

        return result

    def reset(self, scope: str, scope_id: str) -> None:
        """Delete all records for a scope_id.

        Args:
            scope: One of "global", "team", "endpoint", "user".
            scope_id: Identifier within the scope.
        """
        self._validate_scope(scope)

        pk = self._make_pk(scope, scope_id)

        # Query all items with this PK
        response = self._client.query(
            TableName=self._table_name,
            KeyConditionExpression="PK = :pk",
            ExpressionAttributeValues={":pk": {"S": pk}},
            ProjectionExpression="PK, SK",
        )

        # Batch delete
        for item in response.get("Items", []):
            self._client.delete_item(
                TableName=self._table_name,
                Key={"PK": item["PK"], "SK": item["SK"]},
            )

    def reset_all(self) -> None:
        """Delete all items in the table.

        Warning: This scans and deletes all items. Use with caution.
        """
        response = self._client.scan(
            TableName=self._table_name,
            ProjectionExpression="PK, SK",
        )

        for item in response.get("Items", []):
            self._client.delete_item(
                TableName=self._table_name,
                Key={"PK": item["PK"], "SK": item["SK"]},
            )

    def create_table(self, wait: bool = True) -> None:
        """Create the DynamoDB table if it doesn't exist.

        Args:
            wait: If True, wait for table to become ACTIVE.
        """
        try:
            self._client.create_table(
                TableName=self._table_name,
                KeySchema=[
                    {"AttributeName": "PK", "KeyType": "HASH"},
                    {"AttributeName": "SK", "KeyType": "RANGE"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "PK", "AttributeType": "S"},
                    {"AttributeName": "SK", "AttributeType": "S"},
                ],
                BillingMode="PAY_PER_REQUEST",
                TimeToLiveSpecification={
                    "Enabled": True,
                    "AttributeName": "ttl",
                },
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceInUseException":
                return  # Table already exists
            raise

        if wait:
            waiter = self._client.get_waiter("table_exists")
            waiter.wait(TableName=self._table_name)
