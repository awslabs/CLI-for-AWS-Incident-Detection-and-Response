from typing import Any, Callable, Dict, List, Optional

from botocore.exceptions import ClientError
from injector import inject
from mypy_boto3_cloudwatch import CloudWatchClient
from mypy_boto3_cloudwatch.type_defs import MetricAlarmTypeDef
from retry import retry

from aws_idr_customer_cli.data_accessors.base_accessor import BaseAccessor
from aws_idr_customer_cli.utils.constants import BotoServiceName
from aws_idr_customer_cli.utils.log_handlers import CliLogger


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
        return self.create_client(BotoServiceName.CLOUDWATCH, region)

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
