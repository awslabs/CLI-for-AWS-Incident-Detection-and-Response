from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from botocore.exceptions import ClientError
from injector import inject
from mypy_boto3_cloudwatch import CloudWatchClient
from mypy_boto3_cloudwatch.type_defs import MetricAlarmTypeDef
from retry import retry

from aws_idr_customer_cli.data_accessors.base_accessor import BaseAccessor
from aws_idr_customer_cli.utils.log_handlers import CliLogger

CLOUDWATCH_SERVICE_NAME = "cloudwatch"
DEFAULT_LAMBDA_INVOCATION_LOOKBACK_MINUTES = 5
LAMBDA_INVOCATION_METRIC_PERIOD_SECONDS = 60


class AlarmAccessor(BaseAccessor):
    """Data accessor for CloudWatch alarms."""

    MAX_RETRIES = 5

    @inject
    def __init__(
        self, logger: CliLogger, client_factory: Callable[[str, str], CloudWatchClient]
    ) -> None:
        super().__init__(logger, "CloudWatch API")
        self.create_client = client_factory

    def get_client(self, region: str) -> Any:
        """Get CloudWatch client for specified region using cached factory."""
        return self.create_client(CLOUDWATCH_SERVICE_NAME, region)

    @retry(exceptions=ClientError, tries=MAX_RETRIES, delay=1, backoff=2, logger=None)
    def list_alarms_by_prefix(
        self, prefix: str, region: str
    ) -> List[MetricAlarmTypeDef]:
        """
        List CloudWatch alarms by prefix in specified region.

        Args:
            prefix: The prefix to filter alarms by
            region: AWS region to query

        Returns:
            List of matching alarms
        """
        try:
            result = []
            paginator = self.get_client(region).get_paginator("describe_alarms")
            for page in paginator.paginate(AlarmNamePrefix=prefix):
                if "MetricAlarms" in page:
                    result.extend(page["MetricAlarms"])

            self.logger.info(
                f"Found {len(result)} alarms with prefix '{prefix}' in region '{region}'"
            )
            return result

        except ClientError as exception:
            self._handle_error(exception, "list_alarms_by_prefix")
            raise
        except Exception as exception:
            self.logger.error(
                f"Unexpected error in list_alarms_by_prefix: {str(exception)}"
            )
            raise

    @retry(
        exceptions=ClientError, tries=MAX_RETRIES, delay=1.0, backoff=2.0, logger=None
    )
    def get_alarm_by_name(self, name: str, region: str) -> Optional[Any]:
        """
        Get alarm by exact name in specified region.

        Args:
            name: The exact alarm name to search for
            region: AWS region to query

        Returns:
            Alarm details
        """
        try:
            response = self.get_client(region).describe_alarms(AlarmNames=[name])

            if "MetricAlarms" in response and response["MetricAlarms"]:
                self.logger.info(f"Found alarm '{name}' in region '{region}'")
                return response["MetricAlarms"][0]
            else:
                self.logger.info(f"Alarm '{name}' not found in region '{region}'")
                return None

        except ClientError as exception:
            if exception.response["Error"]["Code"] == "ResourceNotFound":
                self.logger.info(f"Alarm '{name}' not found in region '{region}'")
                return None
            self._handle_error(exception, "get_alarm_by_name")
            raise
        except Exception as exception:
            self.logger.error(
                f"Unexpected error in get_alarm_by_name: {str(exception)}"
            )
            raise

    @retry(
        exceptions=ClientError, tries=MAX_RETRIES, delay=1.0, backoff=2.0, logger=None
    )
    def create_alarm(self, alarm_config: Dict[str, Any], region: str) -> None:
        """
        Create CloudWatch alarm using boto3 API in specified region.

        Args:
            alarm_config: Dictionary with alarm configuration in PascalCase format
                to match the AWS CloudWatch API parameter names.
            region: AWS region to create the alarm in

        Returns:
            None - Success is indicated by not raising an exception
        """
        try:
            client = self.get_client(region)
            client.put_metric_alarm(**alarm_config)

        except ClientError as exception:
            self._handle_error(exception, "create_alarm")
            raise
        except Exception as exception:
            self.logger.error(f"Unexpected error in create_alarm: {str(exception)}")
            raise

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
                f"Found {len(result)} metrics in namespace '{namespace}' in region '{region}'"
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
    ) -> bool:
        """Validate if Lambda has been invoked recently using CloudWatch metrics."""
        try:
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
                                    {"Name": "FunctionName", "Value": function_name}
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
                    self.logger.info(f"Lambda {function_name} has recent invocations")
                    return True

            self.logger.info(f"No recent invocations for Lambda {function_name}")
            return False

        except ClientError as exception:
            self._handle_error(exception, "validate_invoked_lambda")
            raise
        except Exception as exception:
            self.logger.error(
                f"Unexpected error in validate_invoked_lambda: {str(exception)}"
            )
            raise
