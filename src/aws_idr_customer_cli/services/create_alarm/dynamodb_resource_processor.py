"""DynamoDB-specific alarm processing for create-alarms command.

This module handles the specialized logic for Amazon DynamoDB global tables,
including replica region discovery and per-region template expansion for
the ReplicationLatency metric.
"""

import copy
from typing import Any, Callable, Dict, List, Optional

from injector import inject

from aws_idr_customer_cli.data_accessors.dynamodb_accessor import (
    DynamoDbAccessor,
)
from aws_idr_customer_cli.services.file_cache.data import ResourceArn
from aws_idr_customer_cli.utils.log_handlers import CliLogger

RECEIVING_REGION_PLACEHOLDER = "${receiving_region}"
INDEX_NAME_PLACEHOLDER = "${index_name}"


class DynamoDbResourceProcessor:
    """Processor for DynamoDB alarm configurations.

    Handles DynamoDB-specific concerns:
    - Discovering replica regions for global tables via describe_table
    - Expanding per-region templates (${receiving_region}) into N alarms
    - Caching table descriptions per ARN
    """

    @inject
    def __init__(
        self,
        logger: CliLogger,
        dynamodb_accessor: DynamoDbAccessor,
    ) -> None:
        self.logger = logger
        self.dynamodb_accessor = dynamodb_accessor
        self._table_cache: Dict[str, Optional[Dict[str, Any]]] = {}

    def _get_table_description(
        self, table_name: str, region: str, arn: str
    ) -> Optional[Dict[str, Any]]:
        """Retrieve and cache table description.

        Returns cached result on subsequent calls for the same ARN.
        Returns None on API errors.
        """
        if arn in self._table_cache:
            return self._table_cache[arn]

        try:
            table: Dict[str, Any] = dict(
                self.dynamodb_accessor.describe_table(table_name, region)
            )
            self._table_cache[arn] = table
            return table
        except Exception as e:
            self.logger.warning(
                f"Could not describe DynamoDB table for " f"{arn}: {str(e)}"
            )
            self._table_cache[arn] = None
            return None

    def _get_receiving_regions(
        self, table_description: Dict[str, Any], source_region: str
    ) -> List[str]:
        """Extract receiving regions from global table replicas.

        Returns all replica regions except the source region, since
        ReplicationLatency measures latency from source to each
        receiving region.
        """
        replicas = table_description.get("Replicas", [])
        return sorted(
            r["RegionName"]
            for r in replicas
            if r.get("RegionName") and r["RegionName"] != source_region
        )

    def process_dynamodb_resource(
        self,
        resource: ResourceArn,
        templates: List[Dict[str, Any]],
        create_alarm_config_fn: Callable[
            [Dict[str, Any], ResourceArn, bool],
            Optional[Dict[str, Any]],
        ],
        suppress_warnings: bool = False,
    ) -> List[Dict[str, Any]]:
        """Process a DynamoDB resource, expanding per-region templates.

        Processing pipeline:
        1. Classify templates: standard vs per-region
        2. For per-region templates, discover replica regions
        3. Expand per-region templates into one alarm per receiving
           region
        4. Create alarm configurations

        Args:
            resource: ResourceArn for the DynamoDB table
            templates: Alarm templates for the DynamoDB service
            create_alarm_config_fn: Callback to create a single alarm
                config
            suppress_warnings: Whether to suppress warning messages

        Returns:
            List of alarm configuration dictionaries
        """
        if not templates:
            self.logger.warning("No templates found for service: dynamodb")
            return []

        standard_templates: List[Dict[str, Any]] = []
        region_templates: List[Dict[str, Any]] = []
        gsi_templates: List[Dict[str, Any]] = []

        for template in templates:
            config_str = str(template.get("configuration", {}))
            if RECEIVING_REGION_PLACEHOLDER in config_str:
                region_templates.append(template)
            elif INDEX_NAME_PLACEHOLDER in config_str:
                gsi_templates.append(template)
            else:
                standard_templates.append(template)

        configurations: List[Dict[str, Any]] = []

        # Process standard templates normally
        for template in standard_templates:
            alarm_config = create_alarm_config_fn(template, resource, suppress_warnings)
            if alarm_config:
                configurations.append(alarm_config)

        # Process per-region templates only if there are any
        if region_templates:
            receiving_regions = self._discover_receiving_regions(resource)

            if not receiving_regions:
                self.logger.info(
                    f"DynamoDB table {resource.arn} is not a "
                    f"global table or has no remote replicas. "
                    f"Skipping ReplicationLatency alarms."
                )
            else:
                self.logger.info(
                    f"DynamoDB global table has "
                    f"{len(receiving_regions)} receiving "
                    f"region(s): {receiving_regions}"
                )
                for template in region_templates:
                    for region in receiving_regions:
                        resolved = self.resolve_receiving_region(template, region)
                        alarm_config = create_alarm_config_fn(
                            resolved, resource, suppress_warnings
                        )
                        if alarm_config:
                            configurations.append(alarm_config)

        # Process GSI templates only if there are any
        if gsi_templates:
            gsi_names = self._discover_gsi_names(resource)

            if not gsi_names:
                self.logger.info(
                    f"DynamoDB table {resource.arn} has no "
                    f"global secondary indexes. "
                    f"Skipping GSI throttle alarms."
                )
            else:
                self.logger.info(
                    f"DynamoDB table has " f"{len(gsi_names)} GSI(s): {gsi_names}"
                )
                for template in gsi_templates:
                    for index_name in gsi_names:
                        resolved = self.resolve_index_name(template, index_name)
                        alarm_config = create_alarm_config_fn(
                            resolved, resource, suppress_warnings
                        )
                        if alarm_config:
                            configurations.append(alarm_config)

        return configurations

    def _discover_receiving_regions(self, resource: ResourceArn) -> List[str]:
        """Discover receiving regions for a DynamoDB global table."""
        from arnparse import arnparse

        parsed_arn = arnparse(resource.arn)
        table_name = parsed_arn.resource.split("/")[-1]

        table = self._get_table_description(table_name, resource.region, resource.arn)
        if not table:
            return []

        # Check if table is a global table
        if not table.get("Replicas"):
            return []

        return self._get_receiving_regions(table, resource.region)

    def _discover_gsi_names(self, resource: ResourceArn) -> List[str]:
        """Discover GSI names for a DynamoDB table."""
        from arnparse import arnparse

        parsed_arn = arnparse(resource.arn)
        table_name = parsed_arn.resource.split("/")[-1]

        table = self._get_table_description(table_name, resource.region, resource.arn)
        if not table:
            return []

        gsis = table.get("GlobalSecondaryIndexes", [])
        return sorted(g["IndexName"] for g in gsis if g.get("IndexName"))

    @staticmethod
    def resolve_receiving_region(
        template: Dict[str, Any], receiving_region: str
    ) -> Dict[str, Any]:
        """Replace ${receiving_region} in a template.

        Args:
            template: Alarm template dict (deep-copied internally)
            receiving_region: Region string to substitute

        Returns:
            New template dict with ${receiving_region} replaced
        """
        resolved = copy.deepcopy(template)
        config = resolved.get("configuration", {})

        if isinstance(config.get("AlarmName"), str):
            config["AlarmName"] = config["AlarmName"].replace(
                RECEIVING_REGION_PLACEHOLDER, receiving_region
            )

        for dim in config.get("Dimensions", []):
            if isinstance(dim, dict) and isinstance(dim.get("Value"), str):
                dim["Value"] = dim["Value"].replace(
                    RECEIVING_REGION_PLACEHOLDER, receiving_region
                )

        return resolved

    @staticmethod
    def resolve_index_name(template: Dict[str, Any], index_name: str) -> Dict[str, Any]:
        """Replace ${index_name} in a template.

        Args:
            template: Alarm template dict (deep-copied internally)
            index_name: GSI name string to substitute

        Returns:
            New template dict with ${index_name} replaced
        """
        resolved = copy.deepcopy(template)
        config = resolved.get("configuration", {})

        if isinstance(config.get("AlarmName"), str):
            config["AlarmName"] = config["AlarmName"].replace(
                INDEX_NAME_PLACEHOLDER, index_name
            )

        for dim in config.get("Dimensions", []):
            if isinstance(dim, dict) and isinstance(dim.get("Value"), str):
                dim["Value"] = dim["Value"].replace(INDEX_NAME_PLACEHOLDER, index_name)

        return resolved
