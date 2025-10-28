from typing import Any, Dict, List, Optional

from injector import inject
from mypy_boto3_resourcegroupstaggingapi.type_defs import (
    ResourceTagMappingTypeDef,
    TagTypeDef,
)

from aws_idr_customer_cli.core.interactive.ui import InteractiveUI
from aws_idr_customer_cli.data_accessors.resource_tagging_accessor import (
    ResourceTaggingAccessor,
)
from aws_idr_customer_cli.exceptions import MalformedResponseError
from aws_idr_customer_cli.interfaces.resource_finder_service import (
    ResourceFinderServiceInterface,
)
from aws_idr_customer_cli.utils.arn_utils import build_resource_arn_object
from aws_idr_customer_cli.utils.mlo_adapter import MloAdapter
from aws_idr_customer_cli.utils.resource_filtering.functional_resource_config import (
    FUNCTIONAL_RESOURCE_TYPES,
)
from aws_idr_customer_cli.utils.session.interactive_session import STYLE_BLUE

# Constants for tag field names
TAG_KEY_FIELD = "Key"
TAG_VALUE_FIELD = "Value"

# Constants for ASG filtering
ASG_TAG_KEY = "aws:autoscaling:groupName"


class ResourceFinderService(ResourceFinderServiceInterface):
    @inject
    def __init__(self, accessor: ResourceTaggingAccessor, ui: InteractiveUI) -> None:
        self.accessor = accessor
        self.ui = ui

    def find_functional_resources_by_tag(
        self, tag_key: str, tag_value: str, regions: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Find functional resources by tag key and value.

        Args:
            tag_key: The tag key to search for
            tag_value: The tag value to search for
            regions: List of regions to search

        Returns:
            List of parsed functional resources with ResourceArn objects and
            validated tags
        """
        tag_filters = [{"Key": tag_key, "Values": tag_value}]
        return self.find_functional_resources_by_tags(tags=tag_filters, regions=regions)

    def find_functional_resources_by_tags(
        self, tags: List[Dict[str, str]], regions: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Find functional resources by multiple tags.

        Only returns resources that are classified as functional (e.g., EC2
        instances, Lambda functions) and excludes non-functional resources
        (e.g., IAM roles, security groups) that are not relevant for workload
        monitoring.

        Args:
            tags: List of tag filters to search for
            regions: List of regions to search

        Returns:
            List of parsed functional resources with ResourceArn objects and
            validated tags
        """
        return self.find_resources_by_tags(tags, regions, FUNCTIONAL_RESOURCE_TYPES)

    def find_resources_by_tags(
        self,
        tags: List[Dict[str, str]],
        regions: List[str],
        resource_types: List[str],
        resource_label: str = "resources",
    ) -> List[Dict[str, Any]]:
        """
        Find resources by tags with specific resource type filtering.

        Args:
            tags: List of tag filters to search for
            regions: List of regions to search
            resource_types: List of resource types to filter (e.g., ["cloudwatch:alarm"])
            resource_label: Label for display messages (e.g., "alarms", "resources")

        Returns:
            List of parsed resources with ResourceArn objects and validated tags
        """
        all_resources = []

        for region in regions:
            try:
                self.ui.display_info(
                    message=f"Searching for {resource_label} in region: {region}",
                    style=STYLE_BLUE,
                )
                resource_response: List[ResourceTagMappingTypeDef] = (
                    self.accessor.get_resources(
                        region=region,
                        tag_filters=tags,
                        resource_types=resource_types,
                    )
                )
                region_resources = self.parse_get_resources_response(
                    response=resource_response
                )
                if region_resources:
                    self.ui.display_info(
                        message=f"✅ Found {len(region_resources)} "
                        f"{resource_label} in region: {region}",
                        style=STYLE_BLUE,
                    )
                else:
                    self.ui.display_info(f"No matching {resource_label} found")
                all_resources.extend(region_resources)
            except Exception as e:
                self.ui.display_error(f"Error searching in region {region}: {str(e)}")
                continue

        return all_resources

    def find_all_resources(self) -> List[Dict[str, Any]]:
        """
        Find all resources.

        Returns:
            Dictionary mapping resource types to lists of resources
        """
        return []

    @staticmethod
    def find_resource_name_from_tags(tags: List[TagTypeDef]) -> Optional[str]:
        """
        Extract Name tag value from resource tags.

        Args:
            tags: List of tag dictionaries with Key and Value fields

        Returns:
            Name tag value if found, None otherwise
        """
        for tag in tags:
            key = tag.get(TAG_KEY_FIELD, "")
            if isinstance(key, str) and key.lower() == "name":
                value = tag.get(TAG_VALUE_FIELD)
                if isinstance(value, str):
                    return value
        return None

    def _is_asg_instance(self, tags: List[TagTypeDef]) -> bool:
        """
        Check if a resource is an Auto Scaling Group instance.

        Args:
            tags: List of resource tags

        Returns:
            True if the resource has the aws:autoscaling:groupName tag, False otherwise
        """

        for tag in tags:
            if (
                isinstance(tag, dict)
                and tag.get(TAG_KEY_FIELD) == ASG_TAG_KEY
                and tag.get(TAG_VALUE_FIELD)
            ):
                return True
        return False

    @staticmethod
    def _validate_tags(tags: Any, resource_index: int) -> None:
        """
        Validate tags structure and content.

        Args:
            tags: Tags data to validate
            resource_index: Index of the resource being processed (for error
            messages)

        Raises:
            MalformedResponseError: When tags are malformed or missing required
            fields
        """
        if not isinstance(tags, list):
            raise MalformedResponseError(
                f"Tags at index {resource_index} must be a list, got "
                f"{type(tags).__name__}"
            )

        for tag_idx, tag in enumerate(tags):
            if not isinstance(tag, dict):
                raise MalformedResponseError(
                    f"Tag at index {tag_idx} in resource {resource_index} "
                    f"must be a dictionary, got {type(tag).__name__}"
                )

            if TAG_KEY_FIELD not in tag:
                raise MalformedResponseError(
                    f"Tag at index {tag_idx} in resource {resource_index} "
                    f"is missing required '{TAG_KEY_FIELD}' field"
                )

            if TAG_VALUE_FIELD not in tag:
                raise MalformedResponseError(
                    f"Tag at index {tag_idx} in resource {resource_index} "
                    f"is missing required '{TAG_VALUE_FIELD}' field"
                )

            if not isinstance(tag[TAG_KEY_FIELD], str):
                raise MalformedResponseError(
                    f"Tag Key at index {tag_idx} in resource {resource_index} "
                    f"must be a string, got {type(tag[TAG_KEY_FIELD]).__name__}"
                )

            if not isinstance(tag[TAG_VALUE_FIELD], str):
                raise MalformedResponseError(
                    f"Tag Value at index {tag_idx} in resource "
                    f"{resource_index} must be a string, got "
                    f"{type(tag[TAG_VALUE_FIELD]).__name__}"
                )

    def parse_get_resources_response(
        self, response: List[ResourceTagMappingTypeDef]
    ) -> List[Dict[str, Any]]:
        """
        Parse get resources responses into structured data with error handling.

        Args:
            response: List of response dictionaries from get resources method

        Returns:
            List of parsed resources with extracted data
            Format: [
                {
                    "ResourceArn": ResourceArn,
                    "Tags": [{"Key": "key", "Value": "value"}, ...],
                },
                ...
            ]

        Raises:
            MalformedResponseError: When response data is malformed or missing
            required fields
        """
        parsed_resources = []

        for i, resource_data in enumerate(response):
            try:
                resource_arn_str = resource_data.get("ResourceARN", "")

                # Build ResourceArn object (this will validate ARN format)
                resource_arn_obj = build_resource_arn_object(resource_arn_str)

                # Get and validate tags
                tags = resource_data.get("Tags", [])
                self._validate_tags(tags, i)

                # Skip ASG instances from resource discovery
                if self._is_asg_instance(tags):
                    resource_friedly_name = MloAdapter._create_friendly_resource_name(
                        resource_arn_str
                    )
                    self.ui.display_info(
                        f"Skipped - {resource_friedly_name}. "
                        f"Alarms for AutoScaling Group Instances not supported."
                    )
                    continue

                name_tag_value = self.find_resource_name_from_tags(tags)

                if name_tag_value:
                    resource_arn_obj.name = name_tag_value

                # Create the parsed resource entry
                parsed_resource = {"ResourceArn": resource_arn_obj, "Tags": tags}

                parsed_resources.append(parsed_resource)

            except Exception as e:
                raise MalformedResponseError(
                    f"Error parsing get resources response at index {i}: " f"{str(e)}"
                ) from e

        return parsed_resources
