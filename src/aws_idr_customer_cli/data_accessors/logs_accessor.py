from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from botocore.exceptions import ClientError
from injector import inject
from retry import retry

from aws_idr_customer_cli.data_accessors.base_accessor import BaseAccessor
from aws_idr_customer_cli.utils.log_handlers import CliLogger

LOGS_SERVICE_NAME = "logs"
DEFAULT_LOOKBACK_MINUTES = 10


class LogsAccessor(BaseAccessor):
    """Data accessor for CloudWatch Logs."""

    MAX_RETRIES = 5

    @inject
    def __init__(
        self, logger: CliLogger, client_factory: Callable[[str, str], Any]
    ) -> None:
        super().__init__(logger, "CloudWatch Logs API")
        self.create_client = client_factory

    def get_client(self, region: str) -> Any:
        """Get CloudWatch Logs client for specified region."""
        return self.create_client(LOGS_SERVICE_NAME, region)

    @retry(exceptions=ClientError, tries=MAX_RETRIES, delay=1, backoff=2, logger=None)
    def get_log_events(
        self,
        log_group_name: str,
        region: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        lookback_minutes: Optional[int] = None,
        limit: int = 50,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Get log events from CloudWatch Logs."""
        try:
            logs_client = self.get_client(region)

            if start_time is None:
                minutes = lookback_minutes or DEFAULT_LOOKBACK_MINUTES
                start_time = datetime.now(timezone.utc) - timedelta(minutes=minutes)

            start_timestamp = int(start_time.timestamp() * 1000)

            params = {
                "logGroupName": log_group_name,
                "startTime": start_timestamp,
                "limit": limit,
                **kwargs,
            }

            if end_time is not None:
                end_timestamp = int(end_time.timestamp() * 1000)
                if end_timestamp <= start_timestamp:
                    raise ValueError(
                        f"endTime ({end_time}) must be after startTime ({start_time})"
                    )
                params["endTime"] = end_timestamp

            response = logs_client.filter_log_events(**params)

            events: List[Dict[str, Any]] = response.get("events", [])
            self.logger.info(
                f"Retrieved {len(events)} log events from {log_group_name}"
            )
            return events

        except ClientError as exception:
            error_code = exception.response["Error"]["Code"]
            if error_code == "ResourceNotFoundException":
                self.logger.info(
                    f"Log group '{log_group_name}' not found in region '{region}'"
                )
                return []
            elif error_code == "InvalidParameterException":
                self.logger.error(
                    f"Invalid parameters for log group '{log_group_name}'"
                )
                raise
            self._handle_error(exception, "get_log_events")
            raise
        except Exception as exception:
            self.logger.error(f"Unexpected error in get_log_events: {str(exception)}")
            raise
