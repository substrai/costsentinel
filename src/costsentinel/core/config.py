"""Configuration parser for CostSentinel."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class PolicyConfig:
    """Budget policy configuration for a specific scope."""

    scope: str  # "global", "team", "endpoint", "user"
    limit_daily: Optional[float] = None
    limit_monthly: Optional[float] = None
    on_exceed: str = "block"  # "block", "downgrade", "alert"
    max_cost_per_request: Optional[float] = None

    def __post_init__(self) -> None:
        valid_actions = {"block", "downgrade", "alert"}
        if self.on_exceed not in valid_actions:
            raise ValueError(
                f"on_exceed must be one of {valid_actions}, got '{self.on_exceed}'"
            )
        valid_scopes = {"global", "team", "endpoint", "user"}
        if self.scope not in valid_scopes:
            raise ValueError(
                f"scope must be one of {valid_scopes}, got '{self.scope}'"
            )


@dataclass
class CostSentinelConfig:
    """Main configuration for CostSentinel."""

    project_name: str = "default"
    pricing: Dict[str, Dict[str, float]] = field(default_factory=dict)
    policies: List[PolicyConfig] = field(default_factory=list)
    routing: Dict[str, Any] = field(default_factory=dict)
    rate_limits: Dict[str, Any] = field(default_factory=dict)
    alerts: Dict[str, Any] = field(default_factory=dict)
    state_file: str = "costsentinel_state.json"
    attribution_file: str = "costsentinel_attributions.json"

    def get_policy(self, scope: str) -> Optional[PolicyConfig]:
        """Get the policy for a given scope."""
        for policy in self.policies:
            if policy.scope == scope:
                return policy
        return None


def load_config(path: Optional[str] = None) -> CostSentinelConfig:
    """Load CostSentinel configuration from a YAML file.

    Args:
        path: Path to the YAML config file. If None, searches for
              costsentinel.yaml in the current directory and parent directories.

    Returns:
        CostSentinelConfig instance.

    Raises:
        FileNotFoundError: If the config file cannot be found.
        ValueError: If the config file is invalid.
    """
    if path is None:
        path = _find_config_file()

    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(config_path, "r") as f:
        raw = yaml.safe_load(f)

    if raw is None:
        raw = {}

    return _parse_config(raw)


def _find_config_file() -> str:
    """Search for costsentinel.yaml in current and parent directories."""
    current = Path.cwd()
    for directory in [current] + list(current.parents):
        candidate = directory / "costsentinel.yaml"
        if candidate.exists():
            return str(candidate)
        candidate = directory / "costsentinel.yml"
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError(
        "No costsentinel.yaml found in current or parent directories. "
        "Run 'costsentinel init' to create one."
    )


def _parse_config(raw: Dict[str, Any]) -> CostSentinelConfig:
    """Parse raw YAML dict into CostSentinelConfig."""
    policies = []
    raw_policies = raw.get("policies", {})

    for scope in ("global", "team", "endpoint", "user"):
        if scope in raw_policies:
            policy_data = raw_policies[scope]
            policies.append(
                PolicyConfig(
                    scope=scope,
                    limit_daily=policy_data.get("limit_daily"),
                    limit_monthly=policy_data.get("limit_monthly"),
                    on_exceed=policy_data.get("on_exceed", "block"),
                    max_cost_per_request=policy_data.get("max_cost_per_request"),
                )
            )

    return CostSentinelConfig(
        project_name=raw.get("project_name", "default"),
        pricing=raw.get("pricing", {}),
        policies=policies,
        routing=raw.get("routing", {}),
        rate_limits=raw.get("rate_limits", {}),
        alerts=raw.get("alerts", {}),
        state_file=raw.get("state_file", "costsentinel_state.json"),
        attribution_file=raw.get("attribution_file", "costsentinel_attributions.json"),
    )


def generate_default_config() -> str:
    """Generate a default costsentinel.yaml content."""
    return """# CostSentinel Configuration
project_name: my-project

# Model pricing (per 1K tokens)
pricing:
  claude-3.5-sonnet:
    input: 0.003
    output: 0.015
  claude-3-sonnet:
    input: 0.003
    output: 0.015
  claude-3-haiku:
    input: 0.00025
    output: 0.00125
  titan-embed:
    input: 0.0001
    output: 0.0

# Budget policies
policies:
  global:
    limit_daily: 100.0
    limit_monthly: 2000.0
    on_exceed: block
  team:
    limit_daily: 25.0
    limit_monthly: 500.0
    on_exceed: downgrade
  endpoint:
    limit_daily: 10.0
    limit_monthly: 200.0
    on_exceed: alert
  user:
    limit_daily: 5.0
    limit_monthly: 100.0
    on_exceed: block
    max_cost_per_request: 0.50

# Routing configuration
routing:
  default_model: claude-3-haiku
  fallback_model: claude-3-haiku
  upgrade_threshold: 0.8

# Rate limits
rate_limits:
  requests_per_minute: 60
  tokens_per_minute: 100000

# Alert configuration
alerts:
  thresholds: [0.5, 0.75, 0.9]
  channels:
    - type: log
      level: warning
"""
