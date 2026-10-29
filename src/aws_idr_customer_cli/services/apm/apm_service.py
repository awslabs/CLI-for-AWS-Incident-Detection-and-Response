import importlib.resources
import json
import os
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, TypedDict
from urllib.parse import quote

import yaml
from injector import inject
from retry import retry

from aws_idr_customer_cli.core.interactive.ui import InteractiveUI
from aws_idr_customer_cli.data_accessors.cloudformation_accessor import (
    CloudFormationAccessor,
)
from aws_idr_customer_cli.data_accessors.cloudwatch_metrics_accessor import (
    CloudWatchMetricsAccessor,
)
from aws_idr_customer_cli.data_accessors.eventbridge_accessor import EventBridgeAccessor
from aws_idr_customer_cli.data_accessors.logs_accessor import LogsAccessor
from aws_idr_customer_cli.data_accessors.sns_accessor import SnsAccessor
from aws_idr_customer_cli.exceptions import ValidationError
from aws_idr_customer_cli.services.apm.cfn_stack_processor import CfnTemplateProcessor
from aws_idr_customer_cli.services.file_cache.data import ApmSetup
from aws_idr_customer_cli.utils.apm.apm_config import (
    generate_stack_name,
    get_default_generate_only_template_path,
    get_integration_type,
    get_lambda_function_name,
    get_template_file,
)
from aws_idr_customer_cli.utils.apm.apm_constants import (
    APM_DEPLOYMENT_COMPLETE_MESSAGE,
    APM_TEST_CANCELLED,
    APM_TEST_CHECKING,
    APM_TEST_ERROR,
    APM_TEST_EVENT_DOCS,
    APM_TEST_INTEGRATION_MESSAGE,
    APM_TEST_NO_EVENTS_MESSAGE,
    APM_TEST_SKIP_MESSAGE,
    APM_TEST_SUCCESS_MESSAGE,
    APM_TEST_WAITING,
    CFN_FAILED_STATUS,
    DEFAULT_FAILURE_GUIDANCE,
    DEFAULT_LOG_LIMIT,
    DEFAULT_LOG_LOOKBACK_MINUTES,
    ERROR_PARTNER_ARN_MISSING,
    ERROR_SNS_ARN_MISSING,
    ERROR_TEMPLATE_EMPTY,
    ERROR_TEMPLATE_EXISTS,
    ERROR_TEMPLATE_FAILED,
    ERROR_TEMPLATE_LOAD_FAILED,
    ERROR_TEMPLATE_NOT_FOUND,
    ERROR_TEMPLATE_WRITE_FAILED,
    FAILURE_GUIDANCE,
    GENERATE_ONLY_FORMAT_DEFAULT,
    GENERATE_ONLY_FORMAT_YAML,
    GENERATE_ONLY_MANUAL_DEPLOY_COMMAND,
    GENERATE_ONLY_MANUAL_DEPLOY_HEADER,
    GENERATE_ONLY_PARAMETERS_FILENAME_SUFFIX,
    GENERATE_ONLY_PARAMETERS_SAVED_MESSAGE,
    GENERATE_ONLY_TEMPLATE_EXPORTED_MESSAGE,
    GENERATE_ONLY_TEMPLATE_SAVED_MESSAGE,
    MSG_DEPLOYMENT_FAILED,
    MSG_NO_RESOURCES,
    MSG_ROLLBACK_COMPLETE,
    MSG_ROLLBACK_FAILED,
    MSG_ROLLBACK_INITIATED,
    PARAM_APM_NAME,
    PARAM_EVENT_BUS_NAME,
    PARAM_EVENT_BUS_PREFIX,
    PARAM_SNS_TRIGGER,
    RESOURCE_TYPE_LABELS,
    STACK_DEPLOYMENT_TIMEOUT,
    TEMPLATE_ENCODING,
    VALIDATION_MAX_WAIT_TIME,
    VALIDATION_POLL_INTERVAL,
    IntegrationType,
)
from aws_idr_customer_cli.utils.log_handlers import CliLogger


class DeploymentResult(TypedDict, total=False):
    """Type definition for deployment results."""

    success: bool
    stack_name: str
    stack_id: Optional[str]
    resources: Optional[List[Dict[str, Any]]]
    region: Optional[str]
    error: Optional[str]
    failure_reason: Optional[str]
    rollback_initiated: Optional[bool]
    template_only: Optional[bool]
    output_path: Optional[str]
    parameters_path: Optional[str]


class LambdaActivity(NamedTuple):
    """Lambda activity status."""

    has_invocations: bool
    has_logs: bool


@dataclass(frozen=True)
class ValidationResult:
    """Result of Lambda validation."""

    success: bool
    status: str
    message: str


CFN_TEMPLATES_PACKAGE = "aws_idr_customer_cli.utils.apm.cfn_templates"


def _get_failure_guidance(failure_reason: str) -> List[str]:
    """Get appropriate guidance messages based on failure reason."""
    for pattern, messages in FAILURE_GUIDANCE.items():
        if any(keyword in failure_reason for keyword in pattern.split("|")):
            return list(messages) + [DEFAULT_FAILURE_GUIDANCE[-1]]

    return list(DEFAULT_FAILURE_GUIDANCE)


def _generate_stack_url(region: str, stack_identifier: Optional[str] = None) -> str:
    """
    Generate CloudFormation console URL.
    """
    base_url = (
        f"https://{region}.console.aws.amazon.com/"
        f"cloudformation/home?region={region}#/stacks"
    )

    if stack_identifier:
        encoded_id = str(quote(stack_identifier, safe=""))
        url = (
            f"{base_url}/stackinfo?"
            f"filteringText=&filteringStatus=active&viewNested=true&"
            f"stackId={encoded_id}"
        )
        return url

    return base_url


class ApmService:
    """APM service for dynamic CloudFormation deployment."""

    @inject
    def __init__(
        self,
        logger: CliLogger,
        ui: InteractiveUI,
        cloudformation_accessor: CloudFormationAccessor,
        eventbridge_accessor: EventBridgeAccessor,
        sns_accessor: SnsAccessor,
        logs_accessor: LogsAccessor,
        metrics_accessor: CloudWatchMetricsAccessor,
    ) -> None:
        self.logger = logger
        self.ui = ui
        self.cloudformation_accessor = cloudformation_accessor
        self.eventbridge_accessor = eventbridge_accessor
        self.sns_accessor = sns_accessor
        self.logs_accessor = logs_accessor
        self.metrics_accessor = metrics_accessor
        self.template_processor = CfnTemplateProcessor(
            cfn_accessor=cloudformation_accessor
        )
        self._template_files = importlib.resources.files(CFN_TEMPLATES_PACKAGE)

    @lru_cache(maxsize=10)
    def load_cloudformation_template(self, apm_provider: str) -> str:
        """Load CloudFormation template for APM provider with caching."""
        template_file = get_template_file(apm_provider)

        try:
            template_content = self._read_template_file(template_file)
            self._validate_template_content(template_content, template_file)
            self.logger.info(f"Loaded template: {template_file}")
            return template_content

        except (ImportError, AttributeError) as e:
            error_msg = ERROR_TEMPLATE_LOAD_FAILED.format(e)
            self.logger.error(error_msg)
            raise ValueError(error_msg)
        except Exception as e:
            error_msg = ERROR_TEMPLATE_FAILED.format(apm_provider, e)
            self.logger.error(error_msg)
            raise ValueError(error_msg)

    def _read_template_file(self, template_file: str) -> str:
        """Read template file from resources."""
        template_resource = self._template_files / template_file

        if not template_resource.is_file():
            raise ValueError(ERROR_TEMPLATE_NOT_FOUND.format(template_file))

        return template_resource.read_text(encoding=TEMPLATE_ENCODING)

    def _validate_template_content(self, content: str, template_file: str) -> None:
        """Validate template content is not empty."""
        if not content.strip():
            raise ValueError(ERROR_TEMPLATE_EMPTY.format(template_file))

    def deploy_and_monitor_stack(
        self,
        apm_provider: str,
        region: str,
        parameters: Dict[str, str],
        custom_incident_path: Optional[str] = None,
        generate_template_only: bool = False,
        output_path: Optional[str] = None,
        output_format: str = GENERATE_ONLY_FORMAT_DEFAULT,
    ) -> DeploymentResult:
        """Deploy CloudFormation stack with monitoring and resource display.

        When ``generate_template_only`` is True, the processed template is
        written to disk and no stack-mutating or template-validation
        CloudFormation calls are made (neither ValidateTemplate nor
        CreateStack); nothing is created in the account. The interactive flow
        may still perform read-only checks earlier (e.g. STS GetCallerIdentity,
        provider prerequisite validation, and a read-only DescribeStacks
        existing-stack check). This lets security/platform teams inspect the
        template or deploy it through their own CI/CD pipeline.
        """
        stack_name = generate_stack_name(apm_provider)

        try:
            integration_type = get_integration_type(apm_provider)
            self._log_deployment_info(
                apm_provider, integration_type, stack_name, region
            )

            processed_template = self._prepare_template(
                apm_provider,
                integration_type,
                region,
                custom_incident_path,
                validate=not generate_template_only,
            )

            if generate_template_only:
                return self._export_template_to_disk(
                    apm_provider=apm_provider,
                    stack_name=stack_name,
                    region=region,
                    processed_template=processed_template,
                    parameters=parameters,
                    output_path=output_path,
                    output_format=output_format,
                )

            self.ui.display_info(f"🚀 Deploying CloudFormation stack: {stack_name}")
            deploy_response = self.cloudformation_accessor.deploy_stack(
                stack_name=stack_name,
                template_body=processed_template,
                parameters=parameters,
                region=region,
            )
            stack_id = deploy_response.get("StackId", "")

            return self._monitor_deployment(stack_name, region, stack_id)

        except Exception as e:
            self.logger.error(f"Stack deployment error: {e}")
            self.ui.display_error(f"Deployment error: {e}")
            return DeploymentResult(
                success=False,
                error=str(e),
                stack_name=stack_name,
            )

    def _export_template_to_disk(
        self,
        apm_provider: str,
        stack_name: str,
        region: str,
        processed_template: str,
        parameters: Dict[str, str],
        output_path: Optional[str] = None,
        output_format: str = GENERATE_ONLY_FORMAT_DEFAULT,
    ) -> DeploymentResult:
        """Write the processed CloudFormation template and its parameters to disk.

        This is the generate-only counterpart of ``deploy_stack``: the exact
        template body and parameter values the CLI would have passed to
        CreateStack are written out instead. No CloudFormation API calls are
        made. Existing files are never overwritten.

        The template body is written as JSON (default) or YAML per
        ``output_format``. The parameters sidecar is always JSON because
        ``aws cloudformation create-stack --parameters file://`` requires JSON.

        Returns a synthetic successful DeploymentResult flagged with
        ``template_only`` so callers can skip deployment-dependent steps.
        """
        target = output_path or get_default_generate_only_template_path(
            apm_provider, output_format
        )
        template_file = Path(target).expanduser()
        # Derive the parameters sidecar from the FULL template filename (not the
        # stem) so runs that differ only by template extension (.json vs .yaml)
        # produce distinct sidecar files and never collide.
        parameters_file = template_file.with_name(
            template_file.name + GENERATE_ONLY_PARAMETERS_FILENAME_SUFFIX
        )

        # Serialize the template body in the requested format. The processed
        # template is a JSON string; for YAML we round-trip through the parsed
        # object. Parameters stay JSON (CFN --parameters requires JSON).
        template_body = self._format_template_body(processed_template, output_format)

        for existing in (template_file, parameters_file):
            if existing.exists():
                error_msg = ERROR_TEMPLATE_EXISTS.format(path=os.path.abspath(existing))
                self.logger.error(error_msg)
                self.ui.display_error(error_msg)
                return DeploymentResult(
                    success=False,
                    stack_name=stack_name,
                    error=error_msg,
                    template_only=True,
                )

        # Same shape CloudFormation expects for `create-stack --parameters file://`
        parameters_body = json.dumps(
            [{"ParameterKey": k, "ParameterValue": v} for k, v in parameters.items()],
            indent=2,
        )

        try:
            template_file.parent.mkdir(parents=True, exist_ok=True)
            template_file.write_text(template_body, encoding=TEMPLATE_ENCODING)
            parameters_file.write_text(parameters_body, encoding=TEMPLATE_ENCODING)
        except OSError as e:
            # Clean up any partially-written files so a failed export leaves the
            # filesystem unchanged and does not trip the overwrite guard on retry.
            template_file.unlink(missing_ok=True)
            parameters_file.unlink(missing_ok=True)
            error_msg = ERROR_TEMPLATE_WRITE_FAILED.format(
                path=os.path.abspath(template_file), error=e
            )
            self.logger.error(error_msg)
            self.ui.display_error(error_msg)
            return DeploymentResult(
                success=False,
                stack_name=stack_name,
                error=error_msg,
                template_only=True,
            )

        template_path = os.path.abspath(template_file)
        parameters_path = os.path.abspath(parameters_file)
        self.logger.info(f"Template exported to {template_path}")
        self.logger.info(f"Parameters exported to {parameters_path}")

        self.ui.display_info(GENERATE_ONLY_TEMPLATE_EXPORTED_MESSAGE)
        self.ui.display_info(
            GENERATE_ONLY_TEMPLATE_SAVED_MESSAGE.format(path=template_path)
        )
        self.ui.display_info(
            GENERATE_ONLY_PARAMETERS_SAVED_MESSAGE.format(path=parameters_path)
        )
        self.ui.display_info(GENERATE_ONLY_MANUAL_DEPLOY_HEADER)
        self.ui.display_info(
            GENERATE_ONLY_MANUAL_DEPLOY_COMMAND.format(
                stack_name=stack_name,
                path=template_path,
                parameters_path=parameters_path,
                region=region,
            )
        )

        return DeploymentResult(
            success=True,
            stack_name=stack_name,
            region=region,
            template_only=True,
            output_path=template_path,
            parameters_path=parameters_path,
        )

    def _format_template_body(self, processed_template: str, output_format: str) -> str:
        """Return the template body in the requested format.

        The processed template is a JSON string. For JSON we return it as-is;
        for YAML we parse and re-dump. Falls back to the original JSON if YAML
        serialization fails for any reason.
        """
        if output_format != GENERATE_ONLY_FORMAT_YAML:
            return processed_template
        try:
            parsed = json.loads(processed_template)
            return str(
                yaml.safe_dump(parsed, default_flow_style=False, sort_keys=False)
            )
        except (json.JSONDecodeError, yaml.YAMLError) as e:
            self.logger.warning(
                f"Could not convert template to YAML ({e}); writing JSON instead."
            )
            return processed_template

    def _log_deployment_info(
        self,
        apm_provider: str,
        integration_type: IntegrationType,
        stack_name: str,
        region: str,
    ) -> None:
        """Log deployment information."""
        self.logger.info(f"Starting CloudFormation deployment for {apm_provider}")
        self.logger.info(f"Integration type: {integration_type.value}")
        self.logger.info(f"Stack name: {stack_name}")
        self.logger.info(f"Region: {region}")

    def _prepare_template(
        self,
        apm_provider: str,
        integration_type: IntegrationType,
        region: str,
        custom_incident_path: Optional[str],
        validate: bool = True,
    ) -> str:
        """Load and process CloudFormation template."""
        template_content = self.load_cloudformation_template(apm_provider)
        template_result: str = self.template_processor.process_template(
            template_content,
            integration_type,
            apm_provider,
            region,
            custom_incident_path,
            validate=validate,
        )
        return template_result

    def _monitor_deployment(
        self, stack_name: str, region: str, stack_id: str
    ) -> DeploymentResult:
        """Monitor stack deployment and handle completion."""
        stack_url = _generate_stack_url(region, stack_id)

        self.ui.display_info(
            f"⏳ {stack_name} stack deployment in progress "
            f"(typically takes 2-3 minutes)...\n{stack_url}"
        )

        completion_result = self.cloudformation_accessor.wait_for_stack_create(
            stack_name=stack_name,
            region=region,
            timeout=STACK_DEPLOYMENT_TIMEOUT,
        )

        if completion_result["Success"]:
            return self._handle_deployment_success(
                stack_name, region, completion_result
            )

        return self._handle_deployment_failure(stack_name, region, completion_result)

    def _handle_deployment_success(
        self, stack_name: str, region: str, completion_result: Dict[str, Any]
    ) -> DeploymentResult:
        """Handle successful deployment."""
        self.ui.display_info(APM_DEPLOYMENT_COMPLETE_MESSAGE)

        self._enable_termination_protection(stack_name, region)

        resources = self.cloudformation_accessor.get_stack_resources(
            stack_name=stack_name, region=region
        )
        self._display_created_resources(resources)

        return DeploymentResult(
            success=True,
            stack_name=stack_name,
            stack_id=completion_result["StackId"],
            resources=resources,
            region=region,
        )

    def _handle_deployment_failure(
        self, stack_name: str, region: str, completion_result: Dict[str, Any]
    ) -> DeploymentResult:
        """Handle CloudFormation deployment failure with detailed diagnostics."""
        failure_reason = completion_result.get("Reason", "Unknown failure")

        self.ui.display_error(MSG_DEPLOYMENT_FAILED)

        self._display_failed_resources(stack_name, region)

        rollback_success = self._rollback_stack(stack_name, region)
        self._display_failure_guidance(failure_reason, region, stack_name)

        return DeploymentResult(
            success=False,
            stack_name=stack_name,
            failure_reason=failure_reason,
            rollback_initiated=rollback_success,
        )

    def _display_failed_resources(self, stack_name: str, region: str) -> None:
        """Display failed resources from stack events."""
        try:
            events = self.cloudformation_accessor.get_stack_events(stack_name, region)
            failed_events = [
                e for e in events if CFN_FAILED_STATUS in e.get("ResourceStatus", "")
            ][:3]

            for event in failed_events:
                resource = event.get("LogicalResourceId", "Unknown")
                reason = event.get("ResourceStatusReason", "No details")
                self.ui.display_error(
                    f" The following resource(s) failed to create, {resource}: {reason}"
                )
        except Exception as e:
            self.logger.warning(f"Could not retrieve stack events: {e}")

    def _rollback_stack(self, stack_name: str, region: str) -> bool:
        """Rollback stack after failure."""
        self.ui.display_info(MSG_ROLLBACK_INITIATED)
        try:
            self.cloudformation_accessor.delete_stack(stack_name, region)
            self.ui.display_info(MSG_ROLLBACK_COMPLETE)
            return True
        except Exception as rollback_error:
            self.logger.error(f"Rollback failed: {rollback_error}")
            self.ui.display_error(MSG_ROLLBACK_FAILED.format(rollback_error))
            return False

    def _enable_termination_protection(self, stack_name: str, region: str) -> None:
        """Enable termination protection on successfully deployed stack."""
        try:
            self.cloudformation_accessor.update_termination_protection(
                stack_name=stack_name, region=region, enable=True
            )
            self.ui.display_info("🔒 Termination protection enabled for stack")
        except Exception as e:
            self.logger.warning(
                f"Failed to enable termination protection for {stack_name}: {e}"
            )
            self.ui.display_info(
                "⚠️  Could not enable termination protection. "
                "You may enable it manually in the AWS Console if needed."
            )

    def _display_failure_guidance(
        self, failure_reason: str, region: str, stack_name: str
    ) -> None:
        """Display guidance for common deployment failures."""
        self.ui.display_info("\n💡 Next Steps:")

        guidance_messages = _get_failure_guidance(failure_reason)
        cfn_console_url = _generate_stack_url(region)

        for message in guidance_messages:
            formatted_message = message.format(
                cfn_console_url=cfn_console_url, stack_name=stack_name
            )
            self.ui.display_info(formatted_message)

    def _display_created_resources(self, resources: List[Dict[str, Any]]) -> None:
        """Display comprehensive resource information."""
        if not resources:
            self.ui.display_info(MSG_NO_RESOURCES)
            return

        resource_groups = self._group_resources_by_type(resources)
        resource_lines = self._format_resource_groups(resource_groups)

        resources_text = "\n".join(resource_lines)
        self.ui.display_result(
            "📋 Created AWS Resources", {"Resources": resources_text}
        )

    def _group_resources_by_type(
        self, resources: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Group resources by type."""
        resource_groups = defaultdict(list)
        for resource in resources:
            resource_type = resource.get("ResourceType", "Unknown")
            resource_groups[resource_type].append(resource)
        return resource_groups

    def _format_resource_groups(
        self, resource_groups: Dict[str, List[Dict[str, Any]]]
    ) -> List[str]:
        """Format resource groups for display."""
        lines = []
        for resource_type, type_resources in resource_groups.items():
            lines.append(f"\n{resource_type}:")
            for resource in type_resources:
                formatted = self._format_resource(resource, resource_type)
                lines.append(f"  {formatted}")
        return lines

    def _format_resource(self, resource: Dict[str, Any], resource_type: str) -> str:
        """Format a single resource for display."""
        logical_id = resource.get("LogicalResourceId", "Unknown")
        physical_id = resource.get("PhysicalResourceId", "Unknown")

        # Check for specific resource type labels
        for type_key, label in RESOURCE_TYPE_LABELS.items():
            if type_key in resource_type:
                return f"• {label}: {physical_id} ({logical_id})"

        # Default formatting
        return f"• {logical_id}: {physical_id}"

    def build_cfn_parameters(
        self, provider: str, integration_type: IntegrationType, apm_setup: ApmSetup
    ) -> Dict[str, str]:
        """Build CloudFormation parameters based on integration type."""
        clean_provider_name = provider.replace(" ", "")
        parameters = {PARAM_APM_NAME: clean_provider_name}

        if integration_type == IntegrationType.SAAS:
            self._add_saas_parameters(parameters, apm_setup)
        elif integration_type == IntegrationType.SNS:
            self._add_sns_parameters(parameters, apm_setup)

        return parameters

    def _add_saas_parameters(
        self, parameters: Dict[str, str], apm_setup: ApmSetup
    ) -> None:
        """Add SaaS-specific parameters."""
        if not apm_setup.partner_event_source_arn:
            raise ValueError(ERROR_PARTNER_ARN_MISSING)

        parameters[PARAM_EVENT_BUS_NAME] = apm_setup.partner_event_source_arn

        prefix = "/".join(apm_setup.partner_event_source_arn.split("/")[:2])
        parameters[PARAM_EVENT_BUS_PREFIX] = prefix

    def _add_sns_parameters(
        self, parameters: Dict[str, str], apm_setup: ApmSetup
    ) -> None:
        """Add SNS-specific parameters."""
        if not apm_setup.sns_topic_arn:
            raise ValueError(ERROR_SNS_ARN_MISSING)

        parameters[PARAM_SNS_TRIGGER] = apm_setup.sns_topic_arn

    def deploy_non_saas_stack(
        self,
        provider: str,
        region: str,
        custom_incident_path: Optional[str] = None,
        generate_template_only: bool = False,
        output_path: Optional[str] = None,
        output_format: str = GENERATE_ONLY_FORMAT_DEFAULT,
    ) -> DeploymentResult:
        """Deploy Non-SaaS (webhook-based) CloudFormation stack."""
        return self.deploy_and_monitor_stack(
            apm_provider=provider,
            region=region,
            custom_incident_path=custom_incident_path,
            parameters={PARAM_APM_NAME: provider.replace(" ", "")},
            generate_template_only=generate_template_only,
            output_path=output_path,
            output_format=output_format,
        )

    def deploy_saas_or_sns_stack(
        self,
        provider: str,
        region: str,
        integration_type: IntegrationType,
        apm_setup: ApmSetup,
        custom_incident_path: Optional[str] = None,
        generate_template_only: bool = False,
        output_path: Optional[str] = None,
        output_format: str = GENERATE_ONLY_FORMAT_DEFAULT,
    ) -> DeploymentResult:
        """Deploy SaaS or SNS CloudFormation stack."""
        parameters = self.build_cfn_parameters(provider, integration_type, apm_setup)

        return self.deploy_and_monitor_stack(
            apm_provider=provider,
            region=region,
            parameters=parameters,
            custom_incident_path=custom_incident_path,
            generate_template_only=generate_template_only,
            output_path=output_path,
            output_format=output_format,
        )

    def _check_lambda_activity(
        self,
        function_name: str,
        log_group_name: str,
        region: str,
        lookback_minutes: int,
        limit: int,
    ) -> LambdaActivity:
        """Check for Lambda invocations and logs."""
        has_invocations = self.metrics_accessor.validate_invoked_lambda(
            function_name=function_name,
            region=region,
            lookback_minutes=lookback_minutes,
        )
        logs = self.logs_accessor.get_log_events(
            log_group_name=log_group_name,
            region=region,
            lookback_minutes=lookback_minutes,
            limit=limit,
        )
        return LambdaActivity(has_invocations=has_invocations, has_logs=bool(logs))

    def _poll_for_lambda_activity(
        self,
        function_name: str,
        log_group_name: str,
        region: str,
        lookback_minutes: int,
        limit: int,
        max_wait_seconds: int,
        poll_interval: int,
    ) -> ValidationResult:
        """Poll for Lambda activity with retry."""
        tries = max_wait_seconds // poll_interval

        @retry(exceptions=ValidationError, tries=tries, delay=poll_interval)
        def _poll() -> ValidationResult:
            activity = self._check_lambda_activity(
                function_name, log_group_name, region, lookback_minutes, limit
            )

            if activity.has_invocations or activity.has_logs:
                return ValidationResult(
                    success=True, status="success", message=APM_TEST_SUCCESS_MESSAGE
                )

            self.ui.display_info(APM_TEST_CHECKING)
            raise ValidationError("No activity detected")

        return _poll()

    def validate_lambda_logs(
        self,
        provider: str,
        region: str,
        lookback_minutes: int = DEFAULT_LOG_LOOKBACK_MINUTES,
        limit: int = DEFAULT_LOG_LIMIT,
        max_wait_seconds: int = VALIDATION_MAX_WAIT_TIME,
        skip_prompt: bool = False,
        poll_interval: int = VALIDATION_POLL_INTERVAL,
    ) -> ValidationResult:
        """Validate transformation Lambda logs for APM events."""
        function_name = get_lambda_function_name(provider)
        log_group_name = f"/aws/lambda/{function_name}"

        doc_url = APM_TEST_EVENT_DOCS.get(provider)
        if doc_url:
            self.ui.display_info(
                f"📝 To send a test event for {provider}, "
                f"check out this guide: {doc_url}"
            )

        if not skip_prompt and not self.ui.prompt_confirm(
            APM_TEST_INTEGRATION_MESSAGE, default=True
        ):
            return ValidationResult(
                success=False, status="skipped", message=APM_TEST_SKIP_MESSAGE
            )

        self.ui.display_info(APM_TEST_WAITING.format(max_wait_seconds))

        try:
            return self._poll_for_lambda_activity(
                function_name,
                log_group_name,
                region,
                lookback_minutes,
                limit,
                max_wait_seconds,
                poll_interval,
            )
        except ValidationError:
            return ValidationResult(
                success=False, status="timeout", message=APM_TEST_NO_EVENTS_MESSAGE
            )
        except KeyboardInterrupt:
            return ValidationResult(
                success=False, status="cancelled", message=APM_TEST_CANCELLED
            )
        except Exception as e:
            self.logger.error(f"Error validating Lambda logs: {e}")
            return ValidationResult(
                success=False, status="error", message=APM_TEST_ERROR.format(str(e))
            )
