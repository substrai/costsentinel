"""Tests for configuration loading and validation."""

import tempfile
from pathlib import Path

import pytest
import yaml

from costsentinel.core.config import (
    CostSentinelConfig,
    PolicyConfig,
    generate_default_config,
    load_config,
)


class TestPolicyConfig:
    """Test suite for PolicyConfig."""

    def test_valid_policy(self):
        policy = PolicyConfig(
            scope="global",
            limit_daily=100.0,
            limit_monthly=2000.0,
            on_exceed="block",
        )
        assert policy.scope == "global"
        assert policy.limit_daily == 100.0

    def test_invalid_scope_raises(self):
        with pytest.raises(ValueError, match="scope must be one of"):
            PolicyConfig(scope="invalid", on_exceed="block")

    def test_invalid_on_exceed_raises(self):
        with pytest.raises(ValueError, match="on_exceed must be one of"):
            PolicyConfig(scope="global", on_exceed="invalid_action")

    def test_all_valid_scopes(self):
        for scope in ("global", "team", "endpoint", "user"):
            policy = PolicyConfig(scope=scope)
            assert policy.scope == scope

    def test_all_valid_actions(self):
        for action in ("block", "downgrade", "alert"):
            policy = PolicyConfig(scope="global", on_exceed=action)
            assert policy.on_exceed == action

    def test_optional_limits(self):
        policy = PolicyConfig(scope="global")
        assert policy.limit_daily is None
        assert policy.limit_monthly is None
        assert policy.max_cost_per_request is None


class TestCostSentinelConfig:
    """Test suite for CostSentinelConfig."""

    def test_default_config(self):
        config = CostSentinelConfig()
        assert config.project_name == "default"
        assert config.pricing == {}
        assert config.policies == []

    def test_get_policy(self):
        config = CostSentinelConfig(
            policies=[
                PolicyConfig(scope="global", limit_daily=100.0),
                PolicyConfig(scope="team", limit_daily=25.0),
            ]
        )
        assert config.get_policy("global").limit_daily == 100.0
        assert config.get_policy("team").limit_daily == 25.0
        assert config.get_policy("user") is None


class TestLoadConfig:
    """Test suite for load_config."""

    def test_load_valid_config(self, tmp_path):
        config_content = {
            "project_name": "test-project",
            "pricing": {
                "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
            },
            "policies": {
                "global": {
                    "limit_daily": 50.0,
                    "limit_monthly": 1000.0,
                    "on_exceed": "block",
                },
            },
        }

        config_file = tmp_path / "costsentinel.yaml"
        config_file.write_text(yaml.dump(config_content))

        config = load_config(str(config_file))
        assert config.project_name == "test-project"
        assert "claude-3-haiku" in config.pricing
        assert len(config.policies) == 1
        assert config.policies[0].scope == "global"
        assert config.policies[0].limit_daily == 50.0

    def test_load_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.yaml")

    def test_load_empty_config(self, tmp_path):
        config_file = tmp_path / "costsentinel.yaml"
        config_file.write_text("")

        config = load_config(str(config_file))
        assert config.project_name == "default"
        assert config.policies == []

    def test_load_config_with_all_policies(self, tmp_path):
        config_content = {
            "project_name": "full-test",
            "policies": {
                "global": {"limit_daily": 100.0, "on_exceed": "block"},
                "team": {"limit_daily": 25.0, "on_exceed": "downgrade"},
                "endpoint": {"limit_daily": 10.0, "on_exceed": "alert"},
                "user": {
                    "limit_daily": 5.0,
                    "on_exceed": "block",
                    "max_cost_per_request": 0.50,
                },
            },
        }

        config_file = tmp_path / "costsentinel.yaml"
        config_file.write_text(yaml.dump(config_content))

        config = load_config(str(config_file))
        assert len(config.policies) == 4

    def test_generate_default_config(self):
        content = generate_default_config()
        assert "project_name" in content
        assert "pricing" in content
        assert "policies" in content
        assert "claude-3.5-sonnet" in content

        # Should be valid YAML
        parsed = yaml.safe_load(content)
        assert parsed["project_name"] == "my-project"

    def test_load_config_with_custom_state_file(self, tmp_path):
        config_content = {
            "project_name": "custom",
            "state_file": "/tmp/custom_state.json",
            "attribution_file": "/tmp/custom_attr.json",
        }

        config_file = tmp_path / "costsentinel.yaml"
        config_file.write_text(yaml.dump(config_content))

        config = load_config(str(config_file))
        assert config.state_file == "/tmp/custom_state.json"
        assert config.attribution_file == "/tmp/custom_attr.json"
