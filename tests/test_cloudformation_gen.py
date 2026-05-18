"""Tests for CloudFormation template generation."""

import yaml
from costsentinel.deployment.cloudformation import CloudFormationGenerator


class TestCloudFormationGenerator:
    def setup_method(self):
        self.gen = CloudFormationGenerator(project_name="myproject", stage="prod")

    def test_generates_valid_yaml(self):
        output = self.gen.generate()
        parsed = yaml.safe_load(output)
        assert parsed is not None

    def test_has_transform(self):
        output = self.gen.generate()
        parsed = yaml.safe_load(output)
        assert parsed["Transform"] == "AWS::Serverless-2016-10-31"

    def test_has_dynamodb_table(self):
        output = self.gen.generate()
        parsed = yaml.safe_load(output)
        assert "CostSentinelStateTable" in parsed["Resources"]
        assert parsed["Resources"]["CostSentinelStateTable"]["Type"] == "AWS::DynamoDB::Table"

    def test_has_lambda_layer(self):
        output = self.gen.generate()
        parsed = yaml.safe_load(output)
        assert "CostSentinelLayer" in parsed["Resources"]

    def test_has_report_function(self):
        output = self.gen.generate()
        parsed = yaml.safe_load(output)
        assert "CostReportFunction" in parsed["Resources"]

    def test_has_scheduled_rule(self):
        output = self.gen.generate()
        parsed = yaml.safe_load(output)
        assert "DailyReportRule" in parsed["Resources"]

    def test_has_dashboard(self):
        output = self.gen.generate()
        parsed = yaml.safe_load(output)
        assert "CostSentinelDashboard" in parsed["Resources"]

    def test_has_outputs(self):
        output = self.gen.generate()
        parsed = yaml.safe_load(output)
        assert "StateTableName" in parsed["Outputs"]
        assert "LayerArn" in parsed["Outputs"]

    def test_stage_in_resource_names(self):
        output = self.gen.generate()
        assert "prod" in output

    def test_project_name_in_description(self):
        output = self.gen.generate()
        assert "myproject" in output

    def test_write_template(self, tmp_path):
        path = str(tmp_path / "template.yaml")
        self.gen.write_template(path)
        with open(path) as f:
            content = f.read()
        assert "AWSTemplateFormatVersion" in content
