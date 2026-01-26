from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from botocore.exceptions import ClientError
from injector import inject
from mypy_boto3_cloudwatch import CloudWatchClient
from retry import retry

from aws_idr_customer_cli.data_accessors.base_accessor import BaseAccessor
from aws_idr_customer_cli.utils.constants import MAX_PARALLEL_WORKERS, BotoServiceName
from aws_idr_customer_cli.utils.log_handlers import CliLogger
from aws_idr_customer_cli.utils.region_utils import get_valid_regions

DEFAULT_LAMBDA_INVOCATION_LOOKBACK_MINUTES = 5
LAMBDA_INVOCATION_METRIC_PERIOD_SECONDS = 60


class CloudWatchMetricsAccessor(BaseAccessor):
    """Data accessor for CloudWatch metrics operations."""

    MAX_RETRIES = 5

    @inject
    def __init__(
        self, logger: CliLogger, client_factory: Callable[[str, str], CloudWatchClient]
    ) -> None:
        super().__init__(logger, "CloudWatch Metrics API")
        self.create_client = client_factory

    def get_client(self, region: str) -> Any:
        """Get CloudWatch client for specified region using cached factory."""
        return self.create_client(BotoServiceName.CLOUDWATCH, region)

    @retry(
        exceptions=ClientError, tries=MAX_RETRIES, delay=1.0, backoff=2.0, logger=None
    )
    def list_metrics_by_namespace(
        self, namespace: str, region: str
    ) -> List[Dict[str, Any]]:
        """
        List CloudWatch metrics for a specific namespace in specified region.

        Args:
            namespace: CloudWatch namespace to query
            region: AWS region to query

        Returns:
            List of metrics in the namespace
        """
        try:
            result = []
            paginator = self.get_client(region).get_paginator("list_metrics")
            for page in paginator.paginate(Namespace=namespace):
                if "Metrics" in page:
                    result.extend(page["Metrics"])

            self.logger.info(
                f"Found {len(result)} metrics in namespace "
                f"'{namespace}' in region '{region}'"
            )
            return result

        except ClientError as exception:
            self._handle_error(exception, "list_metrics_by_namespace")
            raise
        except Exception as exception:
            self.logger.error(
                f"Unexpected error in list_metrics_by_namespace: {str(exception)}"
            )
            raise

    @retry(exceptions=ClientError, tries=MAX_RETRIES, delay=1, backoff=2, logger=None)
    def validate_invoked_lambda(
        self,
        function_name: str,
        region: str,
        lookback_minutes: int = DEFAULT_LAMBDA_INVOCATION_LOOKBACK_MINUTES,
        is_lambda_edge: bool = False,
    ) -> bool:
        """
        Validate if Lambda has been invoked recently using CloudWatch metrics.

        For Lambda@Edge functions, the FunctionName dimension always uses the
        prefixed format "us-east-1.{functionName}" in ALL regions, including
        us-east-1 itself. This is because Lambda@Edge functions are always
        deployed from us-east-1 and CloudWatch uses this prefix consistently.

        Args:
            function_name: Lambda function name
            region: AWS region to query
            lookback_minutes: How far back to check for invocations
            is_lambda_edge: Whether this is a Lambda@Edge function

        Returns:
            True if function has recent invocations, False otherwise
        """
        try:
            # Format function name for Lambda@Edge metrics
            # Lambda@Edge always uses prefixed format in ALL regions
            query_function_name = function_name
            if is_lambda_edge:
                query_function_name = f"us-east-1.{function_name}"
                self.logger.debug(
                    f"Formatted Lambda@Edge function name for region "
                    f"{region}: {query_function_name}"
                )

            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(minutes=lookback_minutes)

            response = self.get_client(region).get_metric_data(
                MetricDataQueries=[
                    {
                        "Id": "invocations",
                        "MetricStat": {
                            "Metric": {
                                "Namespace": "AWS/Lambda",
                                "MetricName": "Invocations",
                                "Dimensions": [
                                    {
                                        "Name": "FunctionName",
                                        "Value": query_function_name,
                                    }
                                ],
                            },
                            "Period": LAMBDA_INVOCATION_METRIC_PERIOD_SECONDS,
                            "Stat": "Sum",
                        },
                    }
                ],
                StartTime=start_time,
                EndTime=end_time,
            )

            for result in response.get("MetricDataResults", []):
                values = result.get("Values", [])
                if values and sum(values) > 0:
                    self.logger.info(
                        f"Lambda {function_name} has recent invocations "
                        f"in region {region}"
                    )
                    return True

            self.logger.debug(
                f"No recent invocations for Lambda {function_name} "
                f"in region {region}"
            )
            return False

        except ClientError as exception:
            self._handle_error(exception, "validate_invoked_lambda")
            raise
        except Exception as exception:
            self.logger.error(
                f"Unexpected error in validate_invoked_lambda: {str(exception)}"
            )
            raise

    def find_regions_with_lambda_metrics(
        self,
        function_name: str,
        regions: Optional[List[str]] = None,
        lookback_minutes: int = DEFAULT_LAMBDA_INVOCATION_LOOKBACK_MINUTES,
        is_lambda_edge: bool = False,
    ) -> List[str]:
        """
        Scan multiple regions in parallel to find where Lambda@Edge metrics exist.

        Lambda@Edge functions execute at CloudFront edge locations globally,
        and metrics are published to the region where the function executes,
        not necessarily where the function is defined (us-east-1).

        For Lambda@Edge functions, the FunctionName dimension always uses the
        prefixed format "us-east-1.{functionName}" in ALL regions, including
        us-east-1 itself.

        This method uses ThreadPoolExecutor to check multiple regions
        concurrently, significantly improving performance

        Args:
            function_name: Lambda function name (raw name, without us-east-1
                prefix)
            regions: List of regions to scan (defaults to all available AWS
                regions)
            lookback_minutes: How far back to check for metrics (default 5
                minutes)
            is_lambda_edge: Whether this is a Lambda@Edge function

        Returns:
            List of regions where Lambda metrics were found
        """
        if regions is None:
            regions = get_valid_regions()

        self.logger.info(
            f"Scanning {len(regions)} regions for Lambda@Edge "
            f"metrics for function: {function_name}"
        )

        def check_region(region: str) -> Optional[str]:
            """
            Check a single region for Lambda metrics.

            Args:
                region: AWS region to check

            Returns:
                Region name if metrics found, None otherwise
            """
            try:
                if self.validate_invoked_lambda(
                    function_name, region, lookback_minutes, is_lambda_edge
                ):
                    self.logger.debug(
                        f"Found metrics for {function_name} in region {region}"
                    )
                    return region
            except Exception as e:
                # Log but continue
                self.logger.debug(
                    f"Error checking region {region} for "
                    f"Lambda@Edge metrics: {str(e)}"
                )
            return None

        regions_with_metrics: List[str] = []

        # Conservative worker count to avoid API throttling
        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_WORKERS) as executor:
            future_to_region = {
                executor.submit(check_region, region): region for region in regions
            }

            for future in as_completed(future_to_region):
                result = future.result()
                if result:
                    regions_with_metrics.append(result)

        self.logger.info(
            f"Found Lambda@Edge metrics in {len(regions_with_metrics)} "
            f"regions for function {function_name}: {regions_with_metrics}"
        )

        return regions_with_metrics
