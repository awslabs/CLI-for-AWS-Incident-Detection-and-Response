import json
from typing import Any, Dict, Optional

import aws_idr_customer_cli.utils.apm.lambda_code
from aws_idr_customer_cli.data_accessors.cloudformation_accessor import (
    CloudFormationAccessor,
)
from aws_idr_customer_cli.utils.apm.apm_config import get_default_incident_path
from aws_idr_customer_cli.utils.apm.apm_constants import (
    LAMBDA_CODE_FILES,
    IntegrationType,
)


class CfnTemplateProcessor:
    """Processes CloudFormation templates for APM integrations."""

    def __init__(self, cfn_accessor: CloudFormationAccessor) -> None:
        """Initialize template processor."""
        self.cfn_accessor = cfn_accessor or CloudFormationAccessor()

    def process_template(
        self,
        template_content: str,
        integration_type: IntegrationType,
        apm_provider: str,
        region: str,
        custom_incident_path: Optional[str] = None,
    ) -> str:
        """
        Process CloudFormation template with optional custom incident path.
        """
        try:
            template = json.loads(template_content)
        except json.JSONDecodeError as e:
            raise ValueError(f"Template must be valid JSON: {e}")

        # Use custom path or APM-specific default
        incident_path = custom_incident_path or get_default_incident_path(apm_provider)

        # Load Lambda code from separate file and replace placeholder
        lambda_code = self._load_lambda_code(integration_type)
        template = self._replace_lambda_code_placeholder(template, lambda_code)

        # Update environment variable for incident path
        template = self._update_incident_path_env(template, incident_path)

        processed_template = json.dumps(template, indent=2)
        self._validate_template(processed_template, region)
        return processed_template

    def _load_lambda_code(self, integration_type: IntegrationType) -> str:
        """
        Load Lambda code from separate file based on integration type.
        """
        lambda_file = LAMBDA_CODE_FILES.get(integration_type)
        if not lambda_file:
            supported = ", ".join(t.value for t in LAMBDA_CODE_FILES.keys())
            raise ValueError(
                f"Unsupported integration type '{integration_type.value}'. "
                f"Supported types: {supported}"
            )

        try:
            pkg_path = aws_idr_customer_cli.utils.apm.lambda_code.__path__[0]
            file_path = f"{pkg_path}/{lambda_file}"
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            raise ValueError(f"Lambda code file not found: {lambda_file}")
        except Exception as e:
            raise ValueError(f"Failed to read Lambda code from {lambda_file}: {e}")

    def _replace_lambda_code_placeholder(
        self, template: Dict[str, Any], lambda_code: str
    ) -> Dict[str, Any]:
        """
        Replace Lambda code placeholder with actual code from separate file.
        """
        resources = template.get("Resources", {})
        if not resources:
            raise ValueError("Template missing required 'Resources' section")

        lambda_resource = None
        for resource_name, resource in resources.items():
            if resource.get("Type") == "AWS::Lambda::Function":
                lambda_resource = resource
                break

        if not lambda_resource:
            raise ValueError("Template must contain an AWS::Lambda::Function resource")

        # Replace placeholder with actual Lambda code
        code_block = lambda_resource.get("Properties", {}).get("Code", {})
        if code_block.get("ZipFile") == "{{LAMBDA_CODE_PLACEHOLDER}}":
            # Use raw string to preserve formatting
            lambda_resource["Properties"]["Code"]["ZipFile"] = lambda_code

        return template

    def _update_incident_path_env(
        self, template: Dict[str, Any], incident_path: str
    ) -> Dict[str, Any]:
        """
        Update INCIDENT_PATH environment variable in Lambda function.
        """
        # Find Lambda function resource
        lambda_resource = None
        for resource_name, resource in template.get("Resources", {}).items():
            if resource.get("Type") == "AWS::Lambda::Function":
                lambda_resource = resource
                break

        if lambda_resource:
            props = lambda_resource.get("Properties", {})
            env_vars = props.get("Environment", {}).get("Variables", {})
            if "INCIDENT_PATH" in env_vars:
                env_vars["INCIDENT_PATH"] = incident_path

        return template

    def _validate_template(self, template_body: str, region: str) -> None:
        """Validate CloudFormation template using AWS API."""
        try:
            self.cfn_accessor.validate_template(
                region=region, template_body=template_body
            )
        except Exception as e:
            raise ValueError(f"CloudFormation template validation failed: {e}")
