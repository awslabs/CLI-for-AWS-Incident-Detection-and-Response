"""CloudFront accessor for CloudFront distribution API operations."""

from typing import Any, Callable, Dict, List, Optional

from botocore.exceptions import ClientError
from injector import inject
from retry import retry

from aws_idr_customer_cli.data_accessors.base_accessor import BaseAccessor
from aws_idr_customer_cli.utils.constants import BotoServiceName
from aws_idr_customer_cli.utils.log_handlers import CliLogger

CLOUDFRONT_REGION = "us-east-1"  # CloudFront is global, use us-east-1 endpoint


class CloudFrontAccessor(BaseAccessor):
    """Data accessor for AWS CloudFront API operations.

    This accessor provides pure data access methods for CloudFront operations.
    Business logic such as Lambda@Edge detection is handled by separate services.
    """

    MAX_RETRIES = 3

    @inject
    def __init__(
        self,
        logger: CliLogger,
        client_factory: Callable[[str, str], Any],
    ) -> None:
        """Initialize CloudFrontAccessor.

        Args:
            logger: CLI logger instance
            client_factory: Factory function for creating boto3 clients
        """
        super().__init__(logger, "CloudFront API")
        self.create_client = client_factory

    def _get_client(self) -> Any:
        """Get CloudFront client for us-east-1 region."""
        return self.create_client(BotoServiceName.CLOUDFRONT, CLOUDFRONT_REGION)

    @retry(exceptions=ClientError, tries=MAX_RETRIES, delay=1, backoff=2, logger=None)
    def list_distributions(self) -> List[Dict[str, Any]]:
        """List all CloudFront distributions.

        Returns:
            List of distribution summaries

        Raises:
            ClientError: If API call fails
        """
        try:
            client = self._get_client()
            distributions: List[Dict[str, Any]] = []

            paginator = client.get_paginator("list_distributions")

            for page in paginator.paginate():
                dist_list = page.get("DistributionList", {})
                items = dist_list.get("Items", [])
                distributions.extend(items)

            self.logger.info(f"Found {len(distributions)} CloudFront distributions")
            return distributions

        except ClientError as exception:
            self._handle_error(exception, "list_distributions")
            raise

    @retry(exceptions=ClientError, tries=MAX_RETRIES, delay=1, backoff=2, logger=None)
    def get_distribution(self, dist_id: str) -> Optional[Dict[str, Any]]:
        """Get CloudFront distribution configuration.

        Args:
            dist_id: CloudFront distribution ID

        Returns:
            Distribution configuration dict, or None if not found
        """
        try:
            client = self._get_client()
            response = client.get_distribution(Id=dist_id)
            return dict(response.get("Distribution", {}))  # type: ignore[arg-type]

        except ClientError as exception:
            error_code = exception.response.get("Error", {}).get("Code", "")

            if error_code == "NoSuchDistribution":
                self.logger.warning(f"CloudFront distribution not found: {dist_id}")
                return None

            self._handle_error(exception, "get_distribution")
            raise
