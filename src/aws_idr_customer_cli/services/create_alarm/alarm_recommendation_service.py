import copy
import importlib.resources
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast

import yaml
from arnparse import arnparse
from arnparse.arnparse import Arn
from injector import inject

from aws_idr_customer_cli.core.interactive.ui import InteractiveUI
from aws_idr_customer_cli.data_accessors.apigateway_accessor import ApiGatewayAccessor
from aws_idr_customer_cli.services.file_cache.data import ResourceArn
from aws_idr_customer_cli.utils.create_alarm.alarm_service_config import (
    AwsServices,
    ProjectDirectories,
    ServiceConfigManager,
)
from aws_idr_customer_cli.utils.create_alarm.metric_namespace_validator import (
    MetricNamespaceValidator,
)
from aws_idr_customer_cli.utils.log_handlers import CliLogger

REQUIRED_TEMPLATE_FIELDS = ["name", "configuration", "description", "alarm_type"]


class MetricType(str, Enum):
    """Metric type classification for alarm templates."""

    NATIVE = "NATIVE"
    CONDITIONAL = "CONDITIONAL"
    NON_NATIVE = "NON-NATIVE"


class AlarmRecommendationService:
    """Service for loading and processing alarm templates for create-alarms command integration."""

    @inject
    def __init__(
        self,
        logger: CliLogger,
        namespace_validator: MetricNamespaceValidator,
        apigateway_accessor: ApiGatewayAccessor,
        ui: InteractiveUI,
    ) -> None:
        """
        Initialize AlarmRecommendationService with metric validation capabilities.

        Validation Statistics Tracking:
        The service tracks metric validation results to provide visibility into alarm creation:

        - native_processed: Count of NATIVE metrics processed (no validation needed)
          Example: Lambda Invocations, EC2 CPUUtilization - always exist

        - conditional_validated: CONDITIONAL metrics that exist (alarm created)
          Example: SNS NumberOfMessagesPublishedToDLQ when DLQ is configured

        - conditional_skipped: CONDITIONAL metrics that don't exist (alarm skipped)
          Example: SNS DLQ metrics when DLQ is not configured

        - non_native_validated: NON-NATIVE metrics that exist (alarm created)
          Example: EKS Container Insights metrics when Container Insights enabled

        - non_native_skipped: NON-NATIVE metrics that don't exist (alarm skipped)
          Example: EKS Container Insights metrics when Container Insights not enabled

        Design Decision:
        Statistics help users understand why certain alarms weren't created and guide
        them to enable required features (DLQ, Container Insights, etc.).

        Args:
            logger: CLI logger instance
            namespace_validator: Validator for metric namespace and existence checks
            ui: Interactive UI for customer-facing messages
        """
        self.logger = logger
        self.namespace_validator = namespace_validator
        self.apigateway_accessor = apigateway_accessor
        self.ui = ui
        self.TEMPLATES_PACKAGE = (
            "aws_idr_customer_cli.utils.create_alarm.idr_alarm_templates"
        )

        # Initialize caches for performance
        self._template_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._arn_cache: Dict[str, Tuple[Any, str]] = {}

        # Initialize validation statistics
        self.validation_stats = {
            "native_processed": 0,
            "conditional_validated": 0,
            "conditional_skipped": 0,
            "non_native_validated": 0,
            "non_native_skipped": 0,
        }

        self.logger.debug(f"Templates package: {self.TEMPLATES_PACKAGE}")

    def generate_alarm_configurations(
        self, resources: List[ResourceArn], suppress_warnings: bool = False
    ) -> List[Dict[str, Any]]:
        """Generate alarm configurations for given resources."""
        if not resources:
            self.logger.warning("No resources provided for alarm generation")
            return []

        alarm_configurations = []

        for resource in resources:
            try:
                configurations = self._process_resource(resource, suppress_warnings)
                alarm_configurations.extend(configurations)
            except Exception as e:
                self.logger.error(
                    f"Failed to process resource {resource.arn}: {str(e)}"
                )
                continue

        self.logger.info(f"Generated {len(alarm_configurations)} alarm configurations")
        return alarm_configurations

    def _process_resource(
        self, resource: ResourceArn, suppress_warnings: bool = False
    ) -> List[Dict[str, Any]]:
        """Process a single resource and return its alarm configurations."""
        service_type = self._get_service_type_from_arn(resource.arn)
        if not service_type:
            self.logger.warning(f"Unsupported service for resource: {resource.arn}")
            return []

        templates = self.get_templates_for_service(service_type)
        if not templates:
            self.logger.warning(f"No templates found for service: {service_type}")
            return []

        if service_type in ["ecs", "eks"]:

            available_ci_namespaces = (
                self.namespace_validator.validate_service_namespaces(
                    service_type, resource.region
                )
            )

            templates = self.namespace_validator.filter_templates_by_ci_namespaces(
                templates, available_ci_namespaces
            )

            if available_ci_namespaces:
                self.logger.info(
                    f"✅ Creating alarms for basic + enhanced {service_type.upper()} "
                    f"metrics (includes Container Insights) for resource {resource.arn}"
                )
            else:
                self.logger.info(
                    f"✅ Creating alarms for basic {service_type.upper()} metrics only "
                    f"(Container Insights not detected) for resource {resource.arn}"
                )

        configurations = []
        for template in templates:
            alarm_config = self._create_alarm_configuration(
                template, resource, suppress_warnings
            )
            if alarm_config:
                configurations.append(alarm_config)

        return configurations

    def _get_service_type_from_arn(self, arn: str) -> Optional[str]:
        """Extract and map service type from ARN using optimized config."""
        try:
            parsed_arn = arnparse(arn)
            service_name = parsed_arn.service.lower()

            # Special case: EC2 sub-resources use resource_type to determine service
            if service_name == "ec2" and hasattr(parsed_arn, "resource_type"):
                resource_type = parsed_arn.resource_type
                if resource_type == "vpn-connection":
                    mapped_service = AwsServices.VPN.value
                elif resource_type == "transit-gateway":
                    mapped_service = AwsServices.TRANSITGATEWAY.value
                else:
                    # Regular EC2 instance
                    mapped_service = AwsServices.EC2.value
            else:
                # Map ARN service name to internal service enum value
                mapped_name = ServiceConfigManager.map_arn_service_name(service_name)
                service_enum = ServiceConfigManager.get_service_enum(mapped_name)
                if not service_enum:
                    return None
                mapped_service = service_enum.value

            if ServiceConfigManager.is_service_supported(mapped_service):
                return cast(str, mapped_service)
            return None

        except Exception as e:
            self.logger.error(f"Failed to parse ARN {arn}: {str(e)}")
            return None

    def _create_alarm_configuration(
        self,
        template: Dict[str, Any],
        resource: ResourceArn,
        suppress_warnings: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Create alarm configuration from template and resource with metric validation.

        This method implements intelligent metric validation based on metric classification:

        Metric Types (from template.metric_type):
        1. NATIVE (default): Standard AWS service metrics that always exist
           - Examples: Lambda Invocations, EC2 CPUUtilization, RDS DatabaseConnections
           - Behavior: Skip validation (performance optimization)
           - Rationale: AWS guarantees these metrics exist for all resources

        2. CONDITIONAL: Metrics that only exist when specific features are enabled
           - Examples:
             * SNS NumberOfMessagesPublishedToDLQ (requires DLQ configuration)
             * Lambda message filtering metrics (requires filters configured)
             * DynamoDB ReplicationLatency (requires global tables)
           - Behavior: Validate existence before creating alarm
           - Rationale: Prevents alarm creation failures for unconfigured features

        3. NON-NATIVE: Metrics from optional monitoring solutions
           - Examples: All EKS Container Insights metrics (pod_cpu_utilization, etc.)
           - Behavior: Validate existence before creating alarm
           - Rationale: These metrics require explicit enablement (Container Insights)

        Validation Logic:
        - NATIVE: Increment native_processed counter, skip validation
        - CONDITIONAL/NON-NATIVE: Call validate_metric_exists()
          * If exists: Increment validated counter, create alarm
          * If missing: Increment skipped counter, return None (skip alarm)
        - Expression-based alarms: Skip validation (use math expressions, not single metrics)

        Design Decisions:
        - Performance: 67% fewer API calls by skipping NATIVE validation (70 of 105 metrics)
        - Fail-safe: Missing metrics return None instead of raising exceptions
        - User-friendly: Warning logs explain why alarms are skipped with remediation hints
        - Statistics: Track all validation outcomes for user feedback

        Args:
            template: Alarm template with metric_type, configuration, and metadata
            resource: ResourceArn with ARN, region, and parsed resource details

        Returns:
            Dict with alarm configuration if metric exists/is NATIVE, None if metric missing

        Examples:
            >>> # NATIVE metric - always creates alarm
            >>> config = service._create_alarm_configuration(
            ...     template={"metric_type": "NATIVE", "name": "Lambda-Invocations", ...},
            ...     resource=ResourceArn(arn="arn:aws:lambda:us-west-2:123:function:my-func")
            ... )
            >>> config is not None
            True
            >>> service.validation_stats["native_processed"]
            1

            >>> # CONDITIONAL metric - validates first
            >>> config = service._create_alarm_configuration(
            ...     template={"metric_type": "CONDITIONAL", "name": "SNS-DLQ-Errors", ...},
            ...     resource=ResourceArn(arn="arn:aws:sns:us-west-2:123:my-topic")
            ... )
            >>> # Returns None if DLQ not configured
            >>> service.validation_stats["conditional_skipped"]
            1

            >>> # NON-NATIVE metric - validates first
            >>> config = service._create_alarm_configuration(
            ...     template={"metric_type": "NON-NATIVE", "name": "EKS-Pod-CPU", ...},
            ...     resource=ResourceArn(arn="arn:aws:eks:us-west-2:123:cluster/my-cluster")
            ... )
            >>> # Returns None if Container Insights not enabled
            >>> service.validation_stats["non_native_skipped"]
            1
        """
        try:
            populated_template = self.populate_template_with_resource(
                template, resource
            )

            # Check if template population failed (e.g., unresolved placeholders)
            if populated_template is None:
                return None

            missing_fields = [
                field
                for field in REQUIRED_TEMPLATE_FIELDS
                if not populated_template.get(field)
            ]

            if missing_fields:
                self.logger.error(
                    f"Template missing required fields {missing_fields} "
                    f"for resource {resource.arn} - skipping"
                )
                return None

            # Validate metric existence for CONDITIONAL and NON-NATIVE metrics
            metric_type = template.get("metric_type", MetricType.NATIVE.value)

            if metric_type == MetricType.NATIVE.value:
                # NATIVE metrics always exist, skip validation
                self.validation_stats["native_processed"] += 1
            elif metric_type in [
                MetricType.CONDITIONAL.value,
                MetricType.NON_NATIVE.value,
            ]:
                config = populated_template["configuration"]
                namespace = config.get("Namespace")
                metric_name = config.get("MetricName")
                dimensions = config.get("Dimensions", [])

                # Skip validation if this is an expression-based alarm
                if not metric_name or "Expression" in config:
                    self.logger.debug(
                        f"Skipping metric validation for expression-based alarm: {template.get('name')}"  # noqa: E501
                    )
                else:
                    # Validate metric exists
                    if not self.namespace_validator.validate_metric_exists(
                        namespace=namespace,
                        metric_name=metric_name,
                        dimensions=dimensions,
                        region=resource.region,
                    ):
                        # Track skipped metric
                        if metric_type == MetricType.CONDITIONAL.value:
                            self.validation_stats["conditional_skipped"] += 1
                        else:
                            self.validation_stats["non_native_skipped"] += 1

                        # Log for debugging
                        if not suppress_warnings:
                            self.logger.warning(
                                f"Skipping alarm '{template.get('name')}' - "
                                f"Metric '{metric_name}' not found in namespace '{namespace}'"
                            )
                        return None
                    else:
                        # Track validated metric
                        if metric_type == MetricType.CONDITIONAL.value:
                            self.validation_stats["conditional_validated"] += 1
                        else:
                            self.validation_stats["non_native_validated"] += 1

            return {
                "alarm_name": populated_template["name"],
                "resource_arn": resource.arn,
                "template_config": populated_template["configuration"],
                "description": populated_template["description"],
                "alarm_type": populated_template["alarm_type"],
                "tags": populated_template.get("tags", {}),
            }

        except Exception as e:
            self.logger.error(f"Failed to create alarm configuration: {str(e)}")
            return None

    def get_templates_for_service(self, service_type: str) -> List[Dict[str, Any]]:
        """Get alarm templates for a specific service type using optimized config."""
        if not ServiceConfigManager.is_service_supported(service_type):
            self.logger.error(f"Service type '{service_type}' is not supported")
            return []

        template_file = ServiceConfigManager.get_template_file(service_type)
        if not template_file:
            self.logger.error(
                f"No template file configured for service: {service_type}"
            )
            return []

        filename = Path(template_file).name
        return self._load_template_resource(filename)

    def _load_template_resource(self, filename: str) -> List[Dict[str, Any]]:
        """Load templates from YAML resource with caching."""
        if filename in self._template_cache:
            self.logger.debug(f"Using cached template for {filename}")
            return self._template_cache[filename]

        def cache_empty_result(error_msg: str) -> List[Dict[str, Any]]:
            self.logger.error(error_msg)
            self._template_cache[filename] = []
            return []

        try:
            files = importlib.resources.files(self.TEMPLATES_PACKAGE)
            template_file = files / filename

            if not template_file.is_file():
                return cache_empty_result(f"Template resource not found: {filename}")

            content = template_file.read_text(encoding="utf-8")
            data = yaml.safe_load(content)

            if not data:
                return cache_empty_result(
                    f"Template resource {filename} is empty or invalid YAML"
                )

            templates = data.get(ProjectDirectories.ALARM_TEMPLATES_KEY, [])

            if not isinstance(templates, list):
                return cache_empty_result(f"Templates in {filename} is not a list")

            validated_templates = [
                template for template in templates if isinstance(template, dict)
            ]

            if len(validated_templates) != len(templates):
                invalid_count = len(templates) - len(validated_templates)
                self.logger.warning(
                    f"Skipped {invalid_count} invalid templates in {filename}"
                )

            self.logger.info(
                f"Loaded {len(validated_templates)} templates from {filename}"
            )
            self._template_cache[filename] = validated_templates
            return validated_templates

        except (ImportError, AttributeError) as e:
            return cache_empty_result(f"importlib.resources not available: {str(e)}")
        except yaml.YAMLError as e:
            return cache_empty_result(f"Failed to parse YAML in {filename}: {str(e)}")
        except Exception as e:
            return cache_empty_result(
                f"Failed to load template resource {filename}: {str(e)}"
            )

    def _replace_dimension_placeholders(
        self,
        dimensions: List[Dict[str, Any]],
        resource_identifiers: Dict[str, str],
        context: str = "dimension",
    ) -> bool:
        """Helper to replace placeholders in dimension arrays.

        Returns:
            True if all placeholders resolved, False if any unresolved
        """
        for dimension in dimensions:
            if not isinstance(dimension, dict):
                continue

            value = dimension.get("Value", "")
            if (
                isinstance(value, str)
                and value.startswith("${")
                and value.endswith("}")
            ):
                placeholder = value[2:-1]  # Remove ${ and }
                if placeholder in resource_identifiers:
                    dimension["Value"] = resource_identifiers[placeholder]
                    self.logger.debug(
                        f"Replaced {context} {placeholder} with {resource_identifiers[placeholder]}"
                    )
                else:
                    self.logger.info(
                        f"Could not find value for {context} placeholder: {placeholder}"
                    )
                    return False
        return True

    def populate_template_with_resource(
        self, template: Dict[str, Any], resource_arn: ResourceArn
    ) -> Optional[Dict[str, Any]]:
        """Populate template dimensions and metrics with resource values."""
        # Use deep copy to avoid modifying cached templates with nested structures
        populated_template = copy.deepcopy(template)
        resource_identifiers = self._extract_resource_identifiers(resource_arn)

        if not resource_identifiers:
            return populated_template

        config = populated_template.get("configuration", {})

        # Replace placeholders in AlarmName field within configuration
        alarm_name_config = config.get("AlarmName", "")
        if isinstance(alarm_name_config, str) and resource_identifiers:
            for placeholder, value in resource_identifiers.items():
                alarm_name_config = alarm_name_config.replace(
                    f"${{{placeholder}}}", value
                )
            config["AlarmName"] = alarm_name_config

        # Handle Dimensions placeholders
        dimensions = config.get("Dimensions")
        if isinstance(dimensions, list):
            if not self._replace_dimension_placeholders(
                dimensions, resource_identifiers, "dimension"
            ):
                return None

        # Handle Metrics placeholders (for math expression alarms)
        metrics = config.get("Metrics")
        if isinstance(metrics, list):
            for metric in metrics:
                if not isinstance(metric, dict):
                    continue

                # Handle MetricStat dimensions
                metric_stat = metric.get("MetricStat", {})
                if isinstance(metric_stat, dict):
                    metric_obj = metric_stat.get("Metric", {})
                    if isinstance(metric_obj, dict):
                        metric_dimensions = metric_obj.get("Dimensions", [])
                        if isinstance(metric_dimensions, list):
                            if not self._replace_dimension_placeholders(
                                metric_dimensions,
                                resource_identifiers,
                                "metric dimension",
                            ):
                                return None

        return populated_template

    def _extract_resource_identifiers(
        self, resource_arn: ResourceArn
    ) -> Dict[str, str]:
        """Extract resource identifiers from ARN with caching."""
        arn_str = resource_arn.arn

        if arn_str in self._arn_cache:
            parsed_arn, service = self._arn_cache[arn_str]
        else:
            try:
                parsed_arn = arnparse(arn_str)
                service = parsed_arn.service
                self._arn_cache[arn_str] = (parsed_arn, service)
            except Exception as e:
                self.logger.error(f"Failed to parse ARN '{arn_str}': {str(e)}")
                self._arn_cache[arn_str] = (None, "")
                return {}

        if not parsed_arn or not service:
            return {}

        # Map the service name to the configured service type for extraction rules
        mapped_service = self._get_service_type_from_arn(arn_str)
        if not mapped_service:
            self.logger.error(
                f"Could not map service '{service}' to supported service type"
            )
            return {}

        # Use optimized cached extraction rules lookup with mapped service name
        extraction_rules = ServiceConfigManager.get_arn_extraction_rules(mapped_service)
        if not extraction_rules:
            self.logger.error(
                f"No ARN extraction rules configured for service: {mapped_service}"
                f"(original: {service})"
            )
            return {}

        identifiers: Dict[str, str] = {}
        self._apply_extraction_rules(parsed_arn, extraction_rules, identifiers)
        return identifiers

    def _apply_extraction_rules(
        self,
        parsed_arn: Arn,
        extraction_rules: Dict[str, str],
        identifiers: Dict[str, str],
    ) -> None:
        """Apply extraction rules using parsed ARN."""
        service = parsed_arn.service.lower()
        resource = parsed_arn.resource or ""

        if service == "s3":
            bucket_name = resource.split("/")[0] if resource else ""
            if "bucket" in extraction_rules and bucket_name:
                identifiers[extraction_rules["bucket"]] = bucket_name

        elif service == "apigateway":
            if resource.startswith("/restapis/"):
                parts = resource.split("/")
                if len(parts) >= 3 and "api_id" in extraction_rules:
                    api_id = parts[2]
                    identifiers[extraction_rules["api_id"]] = api_id
                    # Resolve API name from API Gateway service
                    api_name = self.apigateway_accessor.get_rest_api_name(
                        api_id, parsed_arn.region
                    )
                    identifiers["api_name"] = api_name if api_name else api_id
                if len(parts) >= 5 and "stage" in extraction_rules:
                    identifiers[extraction_rules["stage"]] = parts[4]

        elif service == "elasticloadbalancing":
            if hasattr(parsed_arn, "resource_type") and parsed_arn.resource_type:
                resource_parts = resource.split("/")

                if (
                    parsed_arn.resource_type == "loadbalancer"
                    and "loadbalancer" in extraction_rules
                ):
                    # CloudWatch ALB metrics require full dimension: app/name/id or name for CLB
                    if resource.startswith("loadbalancer/"):
                        # Remove loadbalancer/ prefix: loadbalancer/app/my-alb/id -> app/my-alb/id
                        identifiers[extraction_rules["loadbalancer"]] = "/".join(
                            resource_parts[1:]
                        )
                    else:
                        # Already in correct format: app/my-alb/id or my-clb
                        identifiers[extraction_rules["loadbalancer"]] = resource
        elif service == "medialive":
            if (
                hasattr(parsed_arn, "resource_type")
                and parsed_arn.resource_type == "channel"
            ):
                if "channel" in extraction_rules and resource:
                    identifiers[extraction_rules["channel"]] = resource
        elif (
            service == "ecs"
            and hasattr(parsed_arn, "resource_type")
            and parsed_arn.resource_type == "service"
        ):
            if resource:
                service_parts = resource.split("/")
                if len(service_parts) >= 3:
                    if "cluster" in extraction_rules:
                        identifiers[extraction_rules["cluster"]] = service_parts[1]
                    if "service" in extraction_rules:
                        identifiers[extraction_rules["service"]] = service_parts[2]
                elif len(service_parts) >= 2:
                    # Fallback for shorter format: cluster/service
                    if "cluster" in extraction_rules:
                        identifiers[extraction_rules["cluster"]] = service_parts[0]
                    if "service" in extraction_rules:
                        identifiers[extraction_rules["service"]] = service_parts[1]

        else:
            self._handle_standard_resource_extraction(
                parsed_arn, extraction_rules, identifiers, service
            )

    def _handle_standard_resource_extraction(
        self,
        parsed_arn: Arn,
        extraction_rules: Dict[str, str],
        identifiers: Dict[str, str],
        service: str,
    ) -> None:
        """Handle standard resource extraction for both colon and slash separators."""
        resource = parsed_arn.resource or ""

        resource_type = None
        resource_name = None

        if hasattr(parsed_arn, "resource_type") and parsed_arn.resource_type:
            resource_type = parsed_arn.resource_type
            if "/" in resource:
                resource_name = resource.split("/", 1)[1]
            elif ":" in resource:
                resource_name = resource.split(":", 1)[1]
            else:
                # If there's no separator, the resource is the resource name
                resource_name = resource
        else:
            if ":" in resource:
                parts = resource.split(":", 1)
                if len(parts) == 2:
                    resource_type, resource_name = parts
            elif "/" in resource:
                parts = resource.split("/", 1)
                if len(parts) == 2:
                    resource_type, resource_name = parts
            else:
                resource_name = resource

        if resource_type and resource_name and resource_type in extraction_rules:
            identifiers[extraction_rules[resource_type]] = resource_name
        elif resource_name and extraction_rules:
            key = next(iter(extraction_rules.values()))
            identifiers[key] = resource_name
