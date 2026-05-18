"""CloudFormation/SAM template generation for CostSentinel infrastructure."""

from __future__ import annotations

from typing import Any, Dict, Optional

import yaml


class CloudFormationGenerator:
    """Generates SAM/CloudFormation templates for CostSentinel deployment.

    Produces infrastructure for: DynamoDB (state), Lambda Layer,
    API Gateway (reporting endpoint), EventBridge (scheduled reports),
    and CloudWatch (metrics/dashboard).
    """

    def __init__(
        self,
        project_name: str = "costsentinel",
        stage: str = "dev",
    ):
        self.project_name = project_name
        self.stage = stage

    def generate(self, config: Optional[Dict[str, Any]] = None) -> str:
        """Generate complete SAM template as YAML string.

        Args:
            config: Optional CostSentinel config dict for customization.

        Returns:
            YAML string of the SAM template.
        """
        template = self._build_template(config or {})
        return yaml.dump(template, default_flow_style=False, sort_keys=False)

    def _build_template(self, config: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "AWSTemplateFormatVersion": "2010-09-09",
            "Transform": "AWS::Serverless-2016-10-31",
            "Description": f"CostSentinel infrastructure - {self.project_name} ({self.stage})",
            "Globals": {
                "Function": {
                    "Runtime": "python3.12",
                    "Timeout": 30,
                    "MemorySize": 256,
                    "Environment": {
                        "Variables": {
                            "COSTSENTINEL_STAGE": self.stage,
                            "COSTSENTINEL_TABLE": f"{self.project_name}-state-{self.stage}",
                        }
                    },
                }
            },
            "Resources": {
                **self._state_table(),
                **self._lambda_layer(),
                **self._report_function(),
                **self._budget_check_function(),
                **self._scheduled_report_rule(),
                **self._dashboard(),
            },
            "Outputs": {
                "StateTableName": {
                    "Value": {"Ref": "CostSentinelStateTable"},
                    "Description": "DynamoDB table for cost state",
                },
                "LayerArn": {
                    "Value": {"Ref": "CostSentinelLayer"},
                    "Description": "Lambda Layer ARN for CostSentinel",
                },
            },
        }

    def _state_table(self) -> Dict[str, Any]:
        return {
            "CostSentinelStateTable": {
                "Type": "AWS::DynamoDB::Table",
                "Properties": {
                    "TableName": f"{self.project_name}-state-{self.stage}",
                    "BillingMode": "PAY_PER_REQUEST",
                    "AttributeDefinitions": [
                        {"AttributeName": "pk", "AttributeType": "S"},
                        {"AttributeName": "sk", "AttributeType": "S"},
                    ],
                    "KeySchema": [
                        {"AttributeName": "pk", "KeyType": "HASH"},
                        {"AttributeName": "sk", "KeyType": "RANGE"},
                    ],
                    "TimeToLiveSpecification": {
                        "AttributeName": "ttl",
                        "Enabled": True,
                    },
                },
            }
        }

    def _lambda_layer(self) -> Dict[str, Any]:
        return {
            "CostSentinelLayer": {
                "Type": "AWS::Serverless::LayerVersion",
                "Properties": {
                    "LayerName": f"{self.project_name}-layer-{self.stage}",
                    "Description": "CostSentinel cost governance middleware",
                    "ContentUri": "layer/",
                    "CompatibleRuntimes": ["python3.9", "python3.10", "python3.11", "python3.12"],
                },
            }
        }

    def _report_function(self) -> Dict[str, Any]:
        return {
            "CostReportFunction": {
                "Type": "AWS::Serverless::Function",
                "Properties": {
                    "FunctionName": f"{self.project_name}-report-{self.stage}",
                    "Handler": "report_handler.handler",
                    "CodeUri": "functions/report/",
                    "Description": "Generates cost reports on demand",
                    "Policies": [
                        {"DynamoDBReadPolicy": {"TableName": {"Ref": "CostSentinelStateTable"}}},
                    ],
                    "Events": {
                        "ReportApi": {
                            "Type": "Api",
                            "Properties": {
                                "Path": "/report",
                                "Method": "GET",
                            },
                        }
                    },
                },
            }
        }

    def _budget_check_function(self) -> Dict[str, Any]:
        return {
            "BudgetCheckFunction": {
                "Type": "AWS::Serverless::Function",
                "Properties": {
                    "FunctionName": f"{self.project_name}-budget-check-{self.stage}",
                    "Handler": "budget_handler.handler",
                    "CodeUri": "functions/budget/",
                    "Description": "API Gateway authorizer for budget enforcement",
                    "Policies": [
                        {"DynamoDBCrudPolicy": {"TableName": {"Ref": "CostSentinelStateTable"}}},
                    ],
                },
            }
        }

    def _scheduled_report_rule(self) -> Dict[str, Any]:
        return {
            "DailyReportRule": {
                "Type": "AWS::Events::Rule",
                "Properties": {
                    "Name": f"{self.project_name}-daily-report-{self.stage}",
                    "Description": "Triggers daily cost report generation",
                    "ScheduleExpression": "cron(0 8 * * ? *)",
                    "State": "ENABLED",
                    "Targets": [
                        {
                            "Id": "ReportTarget",
                            "Arn": {"Fn::GetAtt": ["CostReportFunction", "Arn"]},
                        }
                    ],
                },
            }
        }

    def _dashboard(self) -> Dict[str, Any]:
        return {
            "CostSentinelDashboard": {
                "Type": "AWS::CloudWatch::Dashboard",
                "Properties": {
                    "DashboardName": f"{self.project_name}-{self.stage}",
                    "DashboardBody": '{"widgets":[]}',
                },
            }
        }

    def write_template(self, output_path: str = "template.yaml") -> None:
        """Write the generated template to a file.

        Args:
            output_path: Path to write the YAML template.
        """
        content = self.generate()
        with open(output_path, "w") as f:
            f.write(content)
