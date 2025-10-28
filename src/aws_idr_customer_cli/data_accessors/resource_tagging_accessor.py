from typing import Any, Callable, Dict, List, Optional, cast

from botocore.exceptions import ClientError
from injector import inject
from mypy_boto3_resourcegroupstaggingapi.type_defs import ResourceTagMappingTypeDef
from retry import retry

from aws_idr_customer_cli.data_accessors.base_accessor import BaseAccessor
from aws_idr_customer_cli.utils.log_handlers import CliLogger

RGTA_API = "resourcegroupstaggingapi"


class ResourceTaggingAccessor(BaseAccessor):
    """Data accessor for AWS Resource Groups Tagging API."""

    MAX_RESOURCES_PER_PAGE = 100
    MAX_RESOURCE_TYPES_PER_CALL = 100  # RGTA API limit
    MAX_RETRIES = 5

    @inject
    def __init__(
        self, logger: CliLogger, client_factory: Callable[[str, str], Any]
    ) -> None:
        super().__init__(logger, "Resource Groups Tagging API")
        self.create_client = client_factory

    def _get_client(self, region: str) -> Any:
        """Get client using cached factory - no instance caching needed."""
        return self.create_client(RGTA_API, region)

    def _batch_rgta_resource_types(
        self, resource_types: List[str], batch_size: int = 100
    ) -> List[List[str]]:
        """
        Split resource types into batches to work within RGTA API limits.

        Args:
            resource_types: List of resource types to batch
            batch_size: Maximum number of resource types per batch (defaults to
                MAX_RESOURCE_TYPES_PER_CALL = 100)

        Returns:
            List of batched resource type lists
        """
        return [
            resource_types[i : i + batch_size]
            for i in range(0, len(resource_types), batch_size)
        ]

    def _get_resources_single_call(
        self,
        region: str,
        tag_filters: Optional[List[Dict[str, Any]]] = None,
        resource_types: Optional[List[str]] = None,
        resources_per_page: int = 100,
    ) -> List[ResourceTagMappingTypeDef]:
        """
        Execute a single get_resources call to RGTA API.

        Args:
            tag_filters: List of tag filters to apply
            resource_types: List of resource types to filter (must be <=
                MAX_RESOURCE_TYPES_PER_CALL)
            resources_per_page: Number of tags per page (max 100)
            region: region for rgta client

        Returns:
            List of resources with their tags
        """
        resources = []
        resources_per_page = min(resources_per_page, self.MAX_RESOURCES_PER_PAGE)

        paginator = self._get_client(region=region).get_paginator("get_resources")

        kwargs: Dict[str, Any] = {}
        if tag_filters:
            kwargs["TagFilters"] = tag_filters
        if resource_types:
            kwargs["ResourceTypeFilters"] = resource_types
        kwargs["ResourcesPerPage"] = resources_per_page
        kwargs["IncludeComplianceDetails"] = False

        self.logger.debug(f"Calling RGTA client paginator with filter: {tag_filters}")
        page_iterator = paginator.paginate(**kwargs)

        for page in page_iterator:
            if "ResourceTagMappingList" in page:
                resources.extend(page["ResourceTagMappingList"])

        return resources

    @retry(exceptions=ClientError, tries=MAX_RETRIES, delay=1, backoff=2, logger=None)
    def get_resources(
        self,
        region: str,
        tag_filters: Optional[List[Dict[str, Any]]] = None,
        resource_types: Optional[List[str]] = None,
        resources_per_page: int = 100,
    ) -> List[ResourceTagMappingTypeDef]:
        """
        Get resources based on tag filters with automatic pagination and batching.

        Automatically handles RGTA API limits by batching resource_types lists
        larger than 100 items.

        Args:
            tag_filters: List of tag filters to apply
            resource_types: List of resource types to filter (automatically
                batched if > 100 items)
            resources_per_page: Number of tags per page (max 100)
            region: region for rgta client

        Returns:
            List of resources with their tags, combined from all batched calls
            if necessary
        """
        try:
            if resource_types is None or len(resource_types) == 0:
                batches: List[Optional[List[str]]] = [resource_types]
            else:
                batches = cast(
                    List[Optional[List[str]]],
                    self._batch_rgta_resource_types(resource_types),
                )
                if len(batches) > 1:
                    self.logger.info(
                        f"Batching {len(resource_types)} resource types into "
                        f"{len(batches)} RGTA calls"
                    )

            all_resources = []

            for batch_idx, batch in enumerate(batches, 1):
                if len(batches) > 1:
                    batch_size = len(batch) if batch else 0
                    self.logger.debug(
                        f"Processing batch {batch_idx}/{len(batches)} with "
                        f"{batch_size} resource types"
                    )

                try:
                    batch_resources = self._get_resources_single_call(
                        region=region,
                        tag_filters=tag_filters,
                        resource_types=batch,
                        resources_per_page=resources_per_page,
                    )
                    all_resources.extend(batch_resources)
                except Exception as e:
                    # Fail fast on any batch error
                    if len(batches) > 1:
                        self.logger.error(f"Error in batch {batch_idx}: {str(e)}")
                    raise e

            if len(batches) > 1:
                self.logger.info(
                    f"Retrieved {len(all_resources)} resources from "
                    f"{len(batches)} batched calls"
                )
            else:
                self.logger.info(f"Retrieved {len(all_resources)} resources")
            return all_resources

        except ClientError as exception:
            super()._handle_error(exception, "get_resources")
            raise
        except Exception as exception:
            self.logger.error(f"Unexpected error in get_resources: {str(exception)}")
            raise

    @retry(exceptions=ClientError, tries=MAX_RETRIES, delay=1, backoff=2, logger=None)
    def get_tag_keys(self) -> List[str]:
        """
        Get all tag keys used in the account. Not used in Beta. Placeholder only

        Args:
            region: AWS region to query

        Returns:
            List of tag keys
        """
        return []

    @retry(exceptions=ClientError, tries=MAX_RETRIES, delay=1, backoff=2, logger=None)
    def get_tag_values(self, key: str) -> List[str]:
        """
        Get all values for a specific tag key. Not used in Beta. Placeholder only

        Args:
            region: AWS region to query
            key: Tag key to get values for

        Returns:
            List of tag values for the specified key
        """
        return []
