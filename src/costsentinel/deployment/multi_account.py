"""Multi-account cost aggregation support."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class AccountCost:
    """Cost data for a single AWS account."""

    account_id: str
    account_name: str
    total_cost: float
    period: str
    breakdown: Dict[str, float] = field(default_factory=dict)


class MultiAccountAggregator:
    """Aggregates costs across multiple AWS accounts.

    Collects cost data from multiple accounts and produces
    unified reports and budget enforcement across the organization.
    """

    def __init__(self, storage_path: str | Path = ".costsentinel_accounts.json"):
        self.storage_path = Path(storage_path)
        self._accounts: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r") as f:
                    self._accounts = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._accounts = {}

    def _save(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, "w") as f:
            json.dump(self._accounts, f, indent=2)

    def register_account(self, account_id: str, account_name: str) -> None:
        """Register an AWS account for cost tracking.

        Args:
            account_id: AWS account ID.
            account_name: Human-readable account name.
        """
        self._accounts[account_id] = {
            "name": account_name,
            "registered_at": time.time(),
            "costs": [],
        }
        self._save()

    def record_cost(
        self,
        account_id: str,
        cost: float,
        breakdown: Optional[Dict[str, float]] = None,
    ) -> None:
        """Record cost for an account.

        Args:
            account_id: AWS account ID.
            cost: Total cost amount.
            breakdown: Optional cost breakdown by category.
        """
        if account_id not in self._accounts:
            self._accounts[account_id] = {"name": account_id, "costs": []}

        self._accounts[account_id]["costs"].append({
            "cost": cost,
            "breakdown": breakdown or {},
            "timestamp": time.time(),
        })
        self._save()

    def get_total_across_accounts(self) -> float:
        """Get total cost across all accounts.

        Returns:
            Sum of all recorded costs.
        """
        total = 0.0
        for account in self._accounts.values():
            for entry in account.get("costs", []):
                total += entry.get("cost", 0.0)
        return total

    def get_per_account_summary(self) -> List[AccountCost]:
        """Get cost summary per account.

        Returns:
            List of AccountCost objects.
        """
        summaries = []
        for account_id, data in self._accounts.items():
            costs = data.get("costs", [])
            total = sum(e.get("cost", 0.0) for e in costs)
            summaries.append(AccountCost(
                account_id=account_id,
                account_name=data.get("name", account_id),
                total_cost=total,
                period="all-time",
            ))
        summaries.sort(key=lambda a: a.total_cost, reverse=True)
        return summaries

    def get_registered_accounts(self) -> List[str]:
        """Get list of registered account IDs."""
        return list(self._accounts.keys())
