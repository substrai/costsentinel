"""Tests for Lambda Layer generation."""

from costsentinel.deployment.lambda_layer import LambdaLayerGenerator


class TestLambdaLayerGenerator:
    def setup_method(self):
        self.gen = LambdaLayerGenerator()

    def test_wrapper_code_is_valid_python(self):
        code = self.gen.generate_wrapper_code()
        compile(code, "<test>", "exec")  # Should not raise

    def test_wrapper_code_has_imports(self):
        code = self.gen.generate_wrapper_code()
        assert "import" in code
        assert "CostMiddleware" in code

    def test_wrapper_code_has_wrap_handler(self):
        code = self.gen.generate_wrapper_code()
        assert "def wrap_handler" in code

    def test_layer_structure_has_files(self):
        files = self.gen.generate_layer_structure()
        assert "python/costsentinel_layer/__init__.py" in files
        assert "python/costsentinel_layer/requirements.txt" in files

    def test_requirements_has_package(self):
        files = self.gen.generate_layer_structure()
        reqs = files["python/costsentinel_layer/requirements.txt"]
        assert "substrai-costsentinel" in reqs

    def test_sam_layer_resource(self):
        resource = self.gen.generate_sam_layer_resource()
        assert "CostSentinelLayer" in resource
        assert resource["CostSentinelLayer"]["Type"] == "AWS::Serverless::LayerVersion"

    def test_sam_layer_runtimes(self):
        resource = self.gen.generate_sam_layer_resource()
        runtimes = resource["CostSentinelLayer"]["Properties"]["CompatibleRuntimes"]
        assert "python3.12" in runtimes
