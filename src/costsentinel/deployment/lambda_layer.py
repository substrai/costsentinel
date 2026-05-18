"""Lambda Layer generation for zero-code CostSentinel integration."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import yaml


class LambdaLayerGenerator:
    """Generates Lambda Layer configuration for CostSentinel.

    Produces the layer structure and handler wrapper code that enables
    zero-code cost governance integration for existing Lambda functions.
    """

    def __init__(self, config_path: str = "costsentinel.yaml"):
        self.config_path = config_path

    def generate_wrapper_code(self) -> str:
        """Generate the Lambda handler wrapper code.

        Returns:
            Python code string for the Lambda Layer wrapper.
        """
        return '''"""CostSentinel Lambda Layer - auto-wraps handlers with cost governance."""

import os
import json
import importlib
from costsentinel import CostMiddleware

# Load config from layer or environment
_CONFIG_PATH = os.environ.get("COSTSENTINEL_CONFIG", "/opt/costsentinel.yaml")
_middleware = None

def _get_middleware():
    global _middleware
    if _middleware is None:
        _middleware = CostMiddleware(_CONFIG_PATH)
    return _middleware

def wrap_handler(handler_func):
    """Wrap a Lambda handler with CostSentinel cost tracking."""
    middleware = _get_middleware()

    def wrapped(event, context):
        user_id = event.get("requestContext", {}).get("authorizer", {}).get("principalId", "anonymous")
        team_id = os.environ.get("COSTSENTINEL_TEAM", "default")
        endpoint = event.get("path", event.get("routeKey", "/unknown"))

        # Pre-check budget
        decision = middleware.budget_enforcer.check(
            scope="endpoint", scope_id=endpoint, estimated_cost=0.01
        )
        if not decision.allowed and decision.action == "block":
            return {
                "statusCode": 429,
                "body": json.dumps({"error": "Budget exceeded", "remaining": decision.remaining}),
            }

        # Execute handler
        response = handler_func(event, context)

        return response

    return wrapped
'''

    def generate_layer_structure(self) -> Dict[str, str]:
        """Generate the complete Lambda Layer file structure.

        Returns:
            Dict mapping file paths to their contents.
        """
        files = {
            "python/costsentinel_layer/__init__.py": self.generate_wrapper_code(),
            "python/costsentinel_layer/requirements.txt": "substrai-costsentinel>=0.4.0\npyyaml>=6.0\n",
        }
        return files

    def generate_sam_layer_resource(self, layer_name: str = "CostSentinelLayer") -> Dict[str, Any]:
        """Generate SAM template resource for the Lambda Layer.

        Args:
            layer_name: Name for the Lambda Layer.

        Returns:
            SAM resource definition dict.
        """
        return {
            layer_name: {
                "Type": "AWS::Serverless::LayerVersion",
                "Properties": {
                    "LayerName": "costsentinel-governance",
                    "Description": "CostSentinel - AI cost governance middleware",
                    "ContentUri": "layer/",
                    "CompatibleRuntimes": ["python3.9", "python3.10", "python3.11", "python3.12"],
                    "RetentionPolicy": "Retain",
                },
            }
        }
