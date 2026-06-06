"""CLI command for infrastructure provisioning.

Generates and deploys SAM/CloudFormation templates for CostSentinel
infrastructure: DynamoDB table, Lambda Layer, and IAM roles.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


SAM_TEMPLATE = {
    "AWSTemplateFormatVersion": "2010-09-09",
    "Transform": "AWS::Serverless-2016-10-31",
    "Description": "CostSentinel infrastructure - DynamoDB state table and Lambda Layer",
    "Parameters": {
        "Environment": {
            "Type": "String",
            "Default": "dev",
            "AllowedValues": ["dev", "staging", "prod"],
        },
        "TableName": {
            "Type": "String",
            "Default": "costsentinel-state",
        },
        "TTLDays": {
            "Type": "Number",
            "Default": 90,
        },
    },
    "Resources": {
        "CostStateTable": {
            "Type": "AWS::DynamoDB::Table",
            "Properties": {
                "TableName": {"Fn::Sub": "${TableName}-${Environment}"},
                "BillingMode": "PAY_PER_REQUEST",
                "KeySchema": [
                    {"AttributeName": "PK", "KeyType": "HASH"},
                    {"AttributeName": "SK", "KeyType": "RANGE"},
                ],
                "AttributeDefinitions": [
                    {"AttributeName": "PK", "AttributeType": "S"},
                    {"AttributeName": "SK", "AttributeType": "S"},
                ],
                "TimeToLiveSpecification": {
                    "AttributeName": "ttl",
                    "Enabled": True,
                },
                "PointInTimeRecoverySpecification": {"PointInTimeRecoveryEnabled": True},
                "Tags": [
                    {"Key": "Service", "Value": "costsentinel"},
                    {"Key": "Environment", "Value": {"Ref": "Environment"}},
                ],
            },
        },
        "CostSentinelLayer": {
            "Type": "AWS::Serverless::LayerVersion",
            "Properties": {
                "LayerName": {"Fn::Sub": "costsentinel-layer-${Environment}"},
                "Description": "CostSentinel middleware layer for Lambda functions",
                "ContentUri": "./layer/",
                "CompatibleRuntimes": ["python3.9", "python3.10", "python3.11", "python3.12"],
                "RetentionPolicy": "Retain",
            },
        },
        "CostSentinelRole": {
            "Type": "AWS::IAM::Role",
            "Properties": {
                "RoleName": {"Fn::Sub": "costsentinel-role-${Environment}"},
                "AssumeRolePolicyDocument": {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"Service": "lambda.amazonaws.com"},
                            "Action": "sts:AssumeRole",
                        }
                    ],
                },
                "Policies": [
                    {
                        "PolicyName": "CostSentinelDynamoDB",
                        "PolicyDocument": {
                            "Version": "2012-10-17",
                            "Statement": [
                                {
                                    "Effect": "Allow",
                                    "Action": [
                                        "dynamodb:GetItem",
                                        "dynamodb:PutItem",
                                        "dynamodb:UpdateItem",
                                        "dynamodb:DeleteItem",
                                        "dynamodb:Query",
                                        "dynamodb:Scan",
                                    ],
                                    "Resource": {"Fn::GetAtt": ["CostStateTable", "Arn"]},
                                }
                            ],
                        },
                    }
                ],
            },
        },
    },
    "Outputs": {
        "TableName": {"Value": {"Ref": "CostStateTable"}},
        "TableArn": {"Value": {"Fn::GetAtt": ["CostStateTable", "Arn"]}},
        "LayerArn": {"Value": {"Ref": "CostSentinelLayer"}},
        "RoleArn": {"Value": {"Fn::GetAtt": ["CostSentinelRole", "Arn"]}},
    },
}


def generate_template(
    output_dir: str = ".",
    environment: str = "dev",
    table_name: str = "costsentinel-state",
) -> str:
    """Generate SAM template for CostSentinel infrastructure.

    Args:
        output_dir: Directory to write the template to.
        environment: Target environment (dev/staging/prod).
        table_name: Base DynamoDB table name.

    Returns:
        Path to the generated template file.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    template = SAM_TEMPLATE.copy()
    template_file = output_path / "template.yaml"

    # Write as JSON (SAM supports both YAML and JSON)
    json_file = output_path / "template.json"
    with open(json_file, "w") as f:
        json.dump(template, f, indent=2)

    return str(json_file)


def deploy(
    environment: str = "dev",
    table_name: str = "costsentinel-state",
    region: str = "us-east-1",
    stack_name: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Deploy CostSentinel infrastructure using SAM/CloudFormation.

    Args:
        environment: Target environment.
        table_name: Base DynamoDB table name.
        region: AWS region.
        stack_name: CloudFormation stack name. Defaults to costsentinel-{environment}.
        dry_run: If True, only generate template without deploying.

    Returns:
        Dict with deployment results (template_path, stack_name, status).
    """
    if stack_name is None:
        stack_name = f"costsentinel-{environment}"

    # Generate template
    output_dir = f".costsentinel-deploy-{environment}"
    template_path = generate_template(
        output_dir=output_dir,
        environment=environment,
        table_name=table_name,
    )

    result = {
        "template_path": template_path,
        "stack_name": stack_name,
        "environment": environment,
        "region": region,
        "status": "template_generated",
    }

    if dry_run:
        result["status"] = "dry_run_complete"
        return result

    # Deploy using SAM CLI or boto3
    try:
        import boto3

        cf_client = boto3.client("cloudformation", region_name=region)

        with open(template_path, "r") as f:
            template_body = f.read()

        cf_client.create_stack(
            StackName=stack_name,
            TemplateBody=template_body,
            Parameters=[
                {"ParameterKey": "Environment", "ParameterValue": environment},
                {"ParameterKey": "TableName", "ParameterValue": table_name},
            ],
            Capabilities=["CAPABILITY_NAMED_IAM"],
            Tags=[
                {"Key": "Service", "Value": "costsentinel"},
                {"Key": "Environment", "Value": environment},
            ],
        )
        result["status"] = "deploying"
    except ImportError:
        result["status"] = "boto3_not_available"
        result["message"] = "Install boto3 to deploy: pip install substrai-costsentinel[aws]"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

    return result
