"""Lambda@Edge alarm processing for create-alarms command.

This module handles the specialized logic for Lambda@Edge functions which
execute at CloudFront edge locations globally. Lambda@Edge metrics are
published to the region where execution occurs, not us-east-1 where the
function is defined.
"""

from typing import Any, Callable, Dict, List, Optional

from arnparse import arnparse
from injector import inject

from aws_idr_customer_cli.data_accessors.cloudwatch_metrics_accessor import (
    CloudWatchMetricsAccessor,
)
from aws_idr_customer_cli.services.file_cache.data import ResourceArn
from aws_idr_customer_cli.utils.log_handlers import CliLogger
from aws_idr_customer_cli.utils.region_utils import get_valid_regions


class LambdaEdgeProcessor:
    """Processor for Lambda@Edge alarm configurations.

    Lambda@Edge functions execute at CloudFront edge locations globally,
    and metrics are published to the region where execution occurs.
    This processor handles the specialized logic for:
    - Finding regions with Lambda@Edge metrics
    - Creating alarm configurations with region-specific FunctionName dimensions
    - Adding region suffixes to alarm names
    """

    @inject
    def __init__(
        self,
        logger: CliLogger,
        metrics_accessor: CloudWatchMetricsAccessor,
    ) -> None:
        """Initialize LambdaEdgeProcessor.

        Args:
            logger: CLI logger instance
            metrics_accessor: CloudWatch metrics accessor for finding regions
        """
        self.logger = logger
        self.metrics_accessor = metrics_accessor

    def extract_regions_from_alarm_names(self, alarm_names: List[str]) -> List[str]:
        """Extract unique regions from Lambda@Edge alarm name suffixes.

        Lambda@Edge alarm names follow pattern: IDR-Lambda-{MetricType}-{FunctionName}-{region}
        Example: IDR-Lambda-ErrorRate-my-edge-function-us-west-2 -> us-west-2

        Args:
            alarm_names: List of alarm names with region suffixes

        Returns:
            List of unique regions extracted from alarm names
        """
        regions: set[str] = set()
        valid_regions = get_valid_regions()

        for name in alarm_names:
            for region in valid_regions:
                if name.endswith(f"-{region}"):
                    regions.add(region)
                    break

        extracted = list(regions)
        if extracted:
            self.logger.debug(
                f"Extracted {len(extracted)} regions from alarm names: {extracted}"
            )
        return extracted

    def process_lambda_edge_resource(
        self,
        resource: ResourceArn,
        templates: List[Dict[str, Any]],
        create_alarm_config_fn: Callable[
            [Dict[str, Any], ResourceArn, bool], Optional[Dict[str, Any]]
        ],
        suppress_warnings: bool = False,
        cached_regions: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Process Lambda@Edge function and generate alarms for all regions with metrics.

        Lambda@Edge functions execute at CloudFront edge locations globally,
        and metrics are published to the region where execution occurs,
        not necessarily us-east-1 where the function is defined.

        Args:
            resource: ResourceArn for Lambda@Edge function
            templates: List of alarm templates to apply
            create_alarm_config_fn: Callback function to create base alarm configuration
            suppress_warnings: Whether to suppress warning messages
            cached_regions: Optional list of regions from previously stored alarm names.
                When provided, skips metric scanning and uses these regions directly.

        Returns:
            List of alarm configurations (one set per region with metrics)
        """
        # Extract function name from ARN using arnparse
        try:
            parsed_arn = arnparse(resource.arn)
            if not parsed_arn.resource:
                self.logger.error(
                    f"Invalid Lambda ARN format for Lambda@Edge: {resource.arn}"
                )
                return []
            function_name = parsed_arn.resource
        except Exception as e:
            self.logger.error(
                f"Failed to parse Lambda ARN for Lambda@Edge: "
                f"{resource.arn} - {str(e)}"
            )
            return []

        # Use cached_regions if available (from stored alarm names), else scan
        if cached_regions:
            regions_with_metrics = cached_regions
            self.logger.info(
                f"🌐 Lambda@Edge function: {function_name} - "
                f"Using {len(regions_with_metrics)} cached regions from stored "
                f"alarm names: {regions_with_metrics}"
            )
        else:
            self.logger.info(
                f"🌐 Detected Lambda@Edge function: {function_name} - "
                f"Scanning for metrics across CloudFront edge regions"
            )
            regions_with_metrics = (
                self.metrics_accessor.find_regions_with_lambda_metrics(
                    function_name=function_name, is_lambda_edge=True
                )
            )

        if not regions_with_metrics:
            self.logger.warning(
                f"No Lambda@Edge metrics found for function {function_name} "
                f"in any CloudFront edge region. Function may not have been "
                f"invoked recently."
            )
            return []

        if not templates:
            self.logger.warning("No Lambda alarm templates found")
            return []

        all_configurations: List[Dict[str, Any]] = []

        for region in regions_with_metrics:
            # Create a copy of resource with the specific region
            region_resource = ResourceArn(
                type=resource.type, arn=resource.arn, region=region, name=resource.name
            )

            for template in templates:
                # Create alarm config with region-specific modifications
                alarm_config = self.create_lambda_edge_alarm_configuration(
                    template=template,
                    resource=region_resource,
                    metric_region=region,
                    create_alarm_config_fn=create_alarm_config_fn,
                    suppress_warnings=suppress_warnings,
                )
                if alarm_config:
                    all_configurations.append(alarm_config)

        self.logger.info(
            f"Generated {len(all_configurations)} Lambda@Edge alarm "
            f"configurations across {len(regions_with_metrics)} regions"
        )

        return all_configurations

    def create_lambda_edge_alarm_configuration(
        self,
        template: Dict[str, Any],
        resource: ResourceArn,
        metric_region: str,
        create_alarm_config_fn: Callable[
            [Dict[str, Any], ResourceArn, bool], Optional[Dict[str, Any]]
        ],
        suppress_warnings: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Create alarm configuration for Lambda@Edge with region suffix.

        Lambda@Edge metrics require the FunctionName dimension to be in the
        format "us-east-1.{functionName}" rather than just "{functionName}".

        Args:
            template: Alarm template
            resource: ResourceArn with region set to metric region
            metric_region: Region where metrics exist
            create_alarm_config_fn: Callback to create base alarm configuration
            suppress_warnings: Whether to suppress warnings

        Returns:
            Alarm configuration with region suffix in name and updated
            FunctionName dimensions
        """
        config = create_alarm_config_fn(template, resource, suppress_warnings)

        if not config:
            return None

        try:
            parsed_arn = arnparse(resource.arn)
            if not parsed_arn.resource:
                self.logger.error(
                    f"Failed to extract function name from ARN: {resource.arn}"
                )
                return None

            function_name = parsed_arn.resource

            # Lambda@Edge metrics always use prefixed FunctionName dimension:
            # "us-east-1.{functionName}" in ALL regions, including us-east-1
            lambda_edge_function_name = self._get_lambda_edge_function_name(
                function_name, metric_region
            )

            template_config = config.get("template_config", {})

            # Update Dimensions if present (for basic alarms)
            self._update_dimensions(
                template_config.get("Dimensions"), lambda_edge_function_name
            )

            # Update Metrics dimensions if present (for metric math alarms)
            self._update_metrics_dimensions(
                template_config.get("Metrics"), lambda_edge_function_name
            )

        except Exception as e:
            self.logger.error(
                f"Failed to parse Lambda ARN for alarm configuration: "
                f"{resource.arn} - {str(e)}"
            )
            return None

        # Add region suffix to alarm name for Lambda@Edge
        # Pattern: IDR-Lambda-ErrorRate-function-name-region
        # Use the populated AlarmName from template_config (has function name)
        # rather than config["alarm_name"] (raw template name without function name)
        original_alarm_name = config.get("template_config", {}).get(
            "AlarmName", config["alarm_name"]
        )
        config["alarm_name"] = f"{original_alarm_name}-{metric_region}"

        # Update template_config AlarmName as well
        if "template_config" in config and "AlarmName" in config["template_config"]:
            config["template_config"]["AlarmName"] = config["alarm_name"]

        # Mark as Lambda@Edge and set metric region
        config["is_lambda_edge"] = True
        config["metric_region"] = metric_region

        self.logger.debug(
            f"Created Lambda@Edge alarm config: {config['alarm_name']} "
            f"in region {metric_region}"
        )

        return config

    def _get_lambda_edge_function_name(
        self, function_name: str, metric_region: str
    ) -> str:
        """Get the appropriate FunctionName for Lambda@Edge metrics.

        Lambda@Edge metrics always use the prefixed format "us-east-1.{functionName}"
        in ALL regions, including us-east-1 itself. This is because Lambda@Edge
        functions are always deployed from us-east-1 and CloudWatch uses this
        prefix consistently.

        Args:
            function_name: Raw function name from ARN
            metric_region: Region where metrics exist (used for logging)

        Returns:
            Function name formatted for CloudWatch dimensions
        """
        prefixed_name = f"us-east-1.{function_name}"
        self.logger.debug(
            f"Using prefixed function name for region {metric_region}: "
            f"{prefixed_name}"
        )
        return prefixed_name

    def _update_dimensions(
        self, dimensions: Any, lambda_edge_function_name: str
    ) -> None:
        """Update FunctionName in Dimensions array.

        Args:
            dimensions: List of dimension dicts (or None)
            lambda_edge_function_name: The formatted function name to use
        """
        if not isinstance(dimensions, list):
            return

        for dim in dimensions:
            if isinstance(dim, dict) and dim.get("Name") == "FunctionName":
                dim["Value"] = lambda_edge_function_name
                self.logger.debug(
                    f"Updated FunctionName dimension to: {lambda_edge_function_name}"
                )

    def _update_metrics_dimensions(
        self, metrics: Any, lambda_edge_function_name: str
    ) -> None:
        """Update FunctionName in Metrics array for metric math alarms.

        Args:
            metrics: List of metric dicts (or None)
            lambda_edge_function_name: The formatted function name to use
        """
        if not isinstance(metrics, list):
            return

        for metric in metrics:
            if not isinstance(metric, dict):
                continue

            metric_stat = metric.get("MetricStat")
            if not isinstance(metric_stat, dict):
                continue

            metric_obj = metric_stat.get("Metric")
            if not isinstance(metric_obj, dict):
                continue

            metric_dimensions = metric_obj.get("Dimensions", [])
            if not isinstance(metric_dimensions, list):
                continue

            for dim in metric_dimensions:
                if isinstance(dim, dict) and dim.get("Name") == "FunctionName":
                    dim["Value"] = lambda_edge_function_name
                    self.logger.debug(
                        f"Updated metric FunctionName dimension to: "
                        f"{lambda_edge_function_name}"
                    )
