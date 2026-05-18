"""Tests for Terraform module generation."""

from costsentinel.deployment.terraform import TerraformModuleGenerator


class TestTerraformModuleGenerator:
    def setup_method(self):
        self.gen = TerraformModuleGenerator(project_name="myapp", region="eu-west-1", stage="staging")

    def test_main_tf_has_provider(self):
        content = self.gen.generate_main_tf()
        assert 'provider "aws"' in content

    def test_main_tf_has_dynamodb(self):
        content = self.gen.generate_main_tf()
        assert "aws_dynamodb_table" in content

    def test_main_tf_has_lambda_layer(self):
        content = self.gen.generate_main_tf()
        assert "aws_lambda_layer_version" in content

    def test_main_tf_has_iam_role(self):
        content = self.gen.generate_main_tf()
        assert "aws_iam_role" in content

    def test_variables_tf_has_defaults(self):
        content = self.gen.generate_variables_tf()
        assert "myapp" in content
        assert "staging" in content
        assert "eu-west-1" in content

    def test_outputs_tf_has_arns(self):
        content = self.gen.generate_outputs_tf()
        assert "state_table_arn" in content
        assert "layer_arn" in content
        assert "role_arn" in content

    def test_generate_all_returns_three_files(self):
        files = self.gen.generate_all()
        assert "main.tf" in files
        assert "variables.tf" in files
        assert "outputs.tf" in files

    def test_write_module(self, tmp_path):
        output_dir = str(tmp_path / "terraform")
        self.gen.write_module(output_dir)
        import os
        assert os.path.exists(os.path.join(output_dir, "main.tf"))
        assert os.path.exists(os.path.join(output_dir, "variables.tf"))
        assert os.path.exists(os.path.join(output_dir, "outputs.tf"))
