from typing import Any, Callable, List, cast

from botocore.exceptions import ClientError
from injector import inject
from mypy_boto3_s3.type_defs import MetricsConfigurationTypeDef
from retry import retry

from aws_idr_customer_cli.data_accessors.base_accessor import BaseAccessor
from aws_idr_customer_cli.utils.constants import BotoServiceName, Region
from aws_idr_customer_cli.utils.log_handlers import CliLogger


class S3Accessor(BaseAccessor):
    """Data accessor for S3 operations with multi-region support."""

    MAX_RETRIES = 5

    @inject
    def __init__(
        self,
        logger: CliLogger,
        client_factory: Callable[[str, str], Any],
    ) -> None:
        super().__init__(logger, "S3 API")
        self.create_client = client_factory

    def _get_client(self, region: str) -> Any:
        """Get S3 client for specified region using cached factory."""
        return self.create_client(BotoServiceName.S3, region)

    def get_bucket_location(self, bucket_name: str) -> str:
        """Get the region where a bucket is located."""
        try:
            client = self._get_client(str(Region.US_EAST_1.value))
            response = client.get_bucket_location(Bucket=bucket_name)
            return response.get("LocationConstraint") or str(Region.US_EAST_1.value)
        except ClientError as e:
            self._handle_error(e, "get_bucket_location")
            raise

    @retry(exceptions=ClientError, tries=MAX_RETRIES, delay=1, backoff=2, logger=None)
    def list_bucket_metrics_configurations(
        self, bucket_name: str, region: str
    ) -> List[MetricsConfigurationTypeDef]:
        """List S3 bucket metrics configurations."""
        try:
            if region == "global":
                region = self.get_bucket_location(bucket_name)
            client = self._get_client(region)
            response = client.list_bucket_metrics_configurations(Bucket=bucket_name)
            return cast(
                List[MetricsConfigurationTypeDef],
                response.get("MetricsConfigurationList", []),
            )
        except ClientError as exception:
            self._handle_error(exception, "list_bucket_metrics_configurations")
            raise
        except Exception as exception:
            self.logger.error(
                f"Unexpected error in list_bucket_metrics_configurations: "
                f"{str(exception)}"
            )
            raise
