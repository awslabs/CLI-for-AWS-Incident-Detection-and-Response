import json
from typing import Any, Dict, Optional

import aws_idr_customer_cli.utils.apm.lambda_code
from aws_idr_customer_cli.data_accessors.cloudformation_accessor import (
    CloudFormationAccessor,
)
from aws_idr_customer_cli.utils.apm.apm_config import (
    get_default_incident_path,
    resolve_provider_enum,
)
from aws_idr_customer_cli.utils.apm.apm_constants import (
    AUTHORIZER_CODE_FILES,
    LAMBDA_CODE_FILES,
    PROVIDER_AUTHORIZER_CODE_FILES,
    PROVIDER_LAMBDA_CODE_FILES,
    ApmProvider,
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
        validate: bool = True,
    ) -> str:
        """
        Process CloudFormation template with optional custom incident path.

        Args:
            validate: When True (default), the processed template is validated
                via the CloudFormation ValidateTemplate API. Set to False for
                offline template generation (e.g. generate-only export) so no AWS API
                call is made.
        """
        try:
            template = json.loads(template_content)
        except json.JSONDecodeError as e:
            raise ValueError(f"Template must be valid JSON: {e}")

        # Use custom path or APM-specific default
        incident_path = custom_incident_path or get_default_incident_path(apm_provider)

        # Load Lambda code: check provider-level override first, then integration type
        lambda_code = self._load_lambda_code(integration_type, apm_provider)
        template = self._replace_lambda_code_placeholder(template, lambda_code)

        # Load and replace authorizer code if template has the placeholder
        authorizer_code = self._load_authorizer_code(integration_type, apm_provider)
        if authorizer_code:
            template = self._replace_authorizer_code_placeholder(
                template, authorizer_code
            )

        # Update environment variable for incident path
        template = self._update_incident_path_env(template, incident_path)

        processed_template = json.dumps(template, indent=2)
        if validate:
            self._validate_template(processed_template, region)
        return processed_template

    def _load_lambda_code(
        self, integration_type: IntegrationType, apm_provider: str = ""
    ) -> str:
        """
        Load Lambda code from separate file.

        Checks provider-level overrides first, then falls back to integration type.
        """
        code = self._load_code_file(
            provider_overrides=PROVIDER_LAMBDA_CODE_FILES,
            type_defaults=LAMBDA_CODE_FILES,
            integration_type=integration_type,
            apm_provider=apm_provider,
        )
        if code is None:
            supported = ", ".join(t.value for t in LAMBDA_CODE_FILES.keys())
            raise ValueError(
                f"Unsupported integration type '{integration_type.value}'. "
                f"Supported types: {supported}"
            )
        return code

    def _load_authorizer_code(
        self, integration_type: IntegrationType, apm_provider: str = ""
    ) -> Optional[str]:
        """
        Load authorizer Lambda code from separate file.

        Returns None if no authorizer code is configured for the integration type,
        allowing templates without authorizers (SAAS, SNS) to skip this step.
        """
        return self._load_code_file(
            provider_overrides=PROVIDER_AUTHORIZER_CODE_FILES,
            type_defaults=AUTHORIZER_CODE_FILES,
            integration_type=integration_type,
            apm_provider=apm_provider,
        )

    def _load_code_file(
        self,
        provider_overrides: Dict[ApmProvider, str],
        type_defaults: Dict[IntegrationType, str],
        integration_type: IntegrationType,
        apm_provider: str = "",
    ) -> Optional[str]:
        """
        Load code from a file, checking provider overrides then integration type defaults.

        Returns None if no file is configured for the given provider/integration type.
        """
        # Check provider-level override first
        code_file = None
        provider_enum = resolve_provider_enum(apm_provider)
        if provider_enum and provider_enum in provider_overrides:
            code_file = provider_overrides[provider_enum]

        # Fall back to integration type mapping
        if not code_file:
            code_file = type_defaults.get(integration_type)
        if not code_file:
            return None

        try:
            pkg_path = aws_idr_customer_cli.utils.apm.lambda_code.__path__[0]
            file_path = f"{pkg_path}/{code_file}"
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            raise ValueError(f"Code file not found: {code_file}")
        except Exception as e:
            raise ValueError(f"Failed to read code from {code_file}: {e}")

    def _replace_authorizer_code_placeholder(
        self, template: Dict[str, Any], authorizer_code: str
    ) -> Dict[str, Any]:
        """
        Replace authorizer Lambda code placeholder with actual code from file.
        """
        resources = template.get("Resources", {})
        for resource in resources.values():
            if resource.get("Type") != "AWS::Lambda::Function":
                continue
            code_block = resource.get("Properties", {}).get("Code", {})
            if code_block.get("ZipFile") == "{{AUTHORIZER_CODE_PLACEHOLDER}}":
                resource["Properties"]["Code"]["ZipFile"] = authorizer_code
                break
        return template

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
