from abc import ABC, abstractmethod
from typing import Any, Dict, List


class ResourceFinderServiceInterface(ABC):
    """Interface for functional resource finder operations."""

    @abstractmethod
    def find_functional_resources_by_tag(
        self, tag_key: str, tag_value: str, regions: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Find functional resources by tag key and value.

        Only returns resources that are classified as functional (e.g., EC2
        instances, Lambda functions) and excludes non-functional resources
        (e.g., IAM roles, security groups).

        Args:
            tag_key: The tag key to search for
            tag_value: The tag value to search for
            regions: list of regions to search in

        Returns:
            List of parsed functional resources with ResourceArn objects and
            validated tags
        """
        pass

    @abstractmethod
    def find_functional_resources_by_tags(
        self, tags: List[Dict[str, str]], regions: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Find functional resources by multiple tags.

        Only returns resources that are classified as functional (e.g., EC2
        instances, Lambda functions) and excludes non-functional resources
        (e.g., IAM roles, security groups).

        Args:
            tags: List of tag filters to search for
            regions: list of regions to search in

        Returns:
            List of parsed functional resources with ResourceArn objects and
            validated tags
        """
        pass

    @abstractmethod
    def find_all_resources(self) -> List[Dict[str, Any]]:
        """
        Find all resources.

        Args:

        Returns:
            Dictionary mapping resource types to lists of resources
        """
        pass
