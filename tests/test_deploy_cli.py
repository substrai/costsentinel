"""Tests for deploy CLI command."""

import json
import os
import tempfile

import pytest

from costsentinel.cli.deploy import generate_template, deploy, SAM_TEMPLATE


def test_sam_template_structure():
    """SAM template should have required sections."""
    assert "AWSTemplateFormatVersion" in SAM_TEMPLATE
    assert "Transform" in SAM_TEMPLATE
    assert "Resources" in SAM_TEMPLATE
    assert "CostStateTable" in SAM_TEMPLATE["Resources"]
    assert "CostSentinelLayer" in SAM_TEMPLATE["Resources"]
    assert "CostSentinelRole" in SAM_TEMPLATE["Resources"]


def test_generate_template_creates_file(tmp_path):
    """generate_template should create a valid JSON template file."""
    result = generate_template(output_dir=str(tmp_path))
    assert os.path.exists(result)
    with open(result) as f:
        template = json.load(f)
    assert "Resources" in template
    assert "CostStateTable" in template["Resources"]


def test_generate_template_valid_json(tmp_path):
    """Generated template should be valid JSON."""
    result = generate_template(output_dir=str(tmp_path))
    with open(result) as f:
        data = json.load(f)
    assert data["Transform"] == "AWS::Serverless-2016-10-31"


def test_deploy_dry_run(tmp_path):
    """Dry run should generate template without deploying."""
    os.chdir(tmp_path)
    result = deploy(environment="dev", dry_run=True)
    assert result["status"] == "dry_run_complete"
    assert result["stack_name"] == "costsentinel-dev"
    assert result["environment"] == "dev"
    assert os.path.exists(result["template_path"])


def test_deploy_custom_stack_name(tmp_path):
    """Should accept custom stack name."""
    os.chdir(tmp_path)
    result = deploy(environment="prod", stack_name="my-custom-stack", dry_run=True)
    assert result["stack_name"] == "my-custom-stack"


def test_deploy_different_environments(tmp_path):
    """Should work for all environments."""
    os.chdir(tmp_path)
    for env in ["dev", "staging", "prod"]:
        result = deploy(environment=env, dry_run=True)
        assert result["environment"] == env
        assert result["status"] == "dry_run_complete"


def test_template_has_outputs():
    """Template should define useful outputs."""
    outputs = SAM_TEMPLATE["Outputs"]
    assert "TableName" in outputs
    assert "TableArn" in outputs
    assert "LayerArn" in outputs
    assert "RoleArn" in outputs


def test_template_dynamodb_has_ttl():
    """DynamoDB table should have TTL enabled."""
    table = SAM_TEMPLATE["Resources"]["CostStateTable"]["Properties"]
    assert table["TimeToLiveSpecification"]["Enabled"] is True
    assert table["TimeToLiveSpecification"]["AttributeName"] == "ttl"
