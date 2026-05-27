"""Tests for environment-specific config overrides."""

import os
import tempfile

import pytest
import yaml

from costsentinel.core.config import load_config, _deep_merge, _apply_environment_overrides


@pytest.fixture
def config_with_envs(tmp_path):
    """Create a config file with environment overrides."""
    config = {
        "project_name": "test-project",
        "state_file": "state.json",
        "policies": {
            "global": {"limit_daily": 100.0, "limit_monthly": 2000.0, "on_exceed": "block"},
            "team": {"limit_daily": 25.0, "on_exceed": "alert"},
        },
        "environments": {
            "dev": {
                "state_file": "/tmp/dev-state.json",
                "policies": {
                    "global": {"limit_daily": 999.0, "on_exceed": "alert"},
                },
            },
            "staging": {
                "policies": {
                    "global": {"limit_daily": 200.0},
                },
            },
            "prod": {
                "state_file": "/var/costsentinel/state.json",
                "policies": {
                    "global": {"limit_daily": 500.0, "limit_monthly": 10000.0},
                    "team": {"limit_daily": 100.0, "on_exceed": "block"},
                },
            },
        },
    }
    config_path = tmp_path / "costsentinel.yaml"
    config_path.write_text(yaml.dump(config))
    return str(config_path)


def test_load_config_dev_environment(config_with_envs):
    """Test loading config with dev environment overrides."""
    config = load_config(path=config_with_envs, env="dev")
    assert config.state_file == "/tmp/dev-state.json"
    policy = config.get_policy("global")
    assert policy.limit_daily == 999.0
    assert policy.on_exceed == "alert"


def test_load_config_prod_environment(config_with_envs):
    """Test loading config with prod environment overrides."""
    config = load_config(path=config_with_envs, env="prod")
    assert config.state_file == "/var/costsentinel/state.json"
    policy = config.get_policy("global")
    assert policy.limit_daily == 500.0
    assert policy.limit_monthly == 10000.0
    team_policy = config.get_policy("team")
    assert team_policy.limit_daily == 100.0
    assert team_policy.on_exceed == "block"


def test_load_config_staging_partial_override(config_with_envs):
    """Test that staging only overrides specified fields."""
    config = load_config(path=config_with_envs, env="staging")
    policy = config.get_policy("global")
    assert policy.limit_daily == 200.0
    # Monthly should remain from base
    assert policy.limit_monthly == 2000.0
    assert config.state_file == "state.json"  # Not overridden


def test_load_config_unknown_env_uses_base(config_with_envs):
    """Test that unknown environment falls back to base config."""
    config = load_config(path=config_with_envs, env="unknown")
    assert config.state_file == "state.json"
    policy = config.get_policy("global")
    assert policy.limit_daily == 100.0


def test_load_config_env_from_environment_variable(config_with_envs, monkeypatch):
    """Test that COSTSENTINEL_ENV environment variable is used."""
    monkeypatch.setenv("COSTSENTINEL_ENV", "prod")
    config = load_config(path=config_with_envs)
    assert config.state_file == "/var/costsentinel/state.json"


def test_load_config_defaults_to_dev(config_with_envs, monkeypatch):
    """Test that default environment is 'dev' when no env specified."""
    monkeypatch.delenv("COSTSENTINEL_ENV", raising=False)
    config = load_config(path=config_with_envs)
    assert config.state_file == "/tmp/dev-state.json"


def test_deep_merge_nested_dicts():
    """Test deep merge with nested dictionaries."""
    base = {"a": {"b": 1, "c": 2}, "d": 3}
    override = {"a": {"b": 10, "e": 5}, "f": 6}
    result = _deep_merge(base, override)
    assert result == {"a": {"b": 10, "c": 2, "e": 5}, "d": 3, "f": 6}


def test_deep_merge_override_replaces_non_dict():
    """Test that non-dict values are replaced entirely."""
    base = {"a": [1, 2, 3], "b": "hello"}
    override = {"a": [4, 5], "b": "world"}
    result = _deep_merge(base, override)
    assert result == {"a": [4, 5], "b": "world"}


def test_apply_environment_overrides_removes_environments_key():
    """Test that environments block is removed from output."""
    raw = {"project_name": "test", "environments": {"dev": {"project_name": "dev-test"}}}
    result = _apply_environment_overrides(raw, "dev")
    assert "environments" not in result
    assert result["project_name"] == "dev-test"


def test_config_without_environments_block(tmp_path):
    """Test that config without environments block works normally."""
    config = {"project_name": "simple", "policies": {"global": {"limit_daily": 50.0, "on_exceed": "alert"}}}
    config_path = tmp_path / "costsentinel.yaml"
    config_path.write_text(yaml.dump(config))
    result = load_config(path=str(config_path), env="prod")
    assert result.project_name == "simple"
