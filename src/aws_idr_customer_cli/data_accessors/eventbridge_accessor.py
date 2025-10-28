from typing import Any, Callable, Optional, cast

from botocore.exceptions import ClientError
from injector import inject
from mypy_boto3_events.type_defs import (
    DescribeEventBusResponseTypeDef,
    DescribeRuleResponseTypeDef,
    ListEventBusesResponseTypeDef,
    ListRulesResponseTypeDef,
)
from retry import retry

from aws_idr_customer_cli.data_accessors.base_accessor import BaseAccessor
from aws_idr_customer_cli.utils.log_handlers import CliLogger

EVENTBRIDGE_SERVICE_NAME = "events"


class EventBridgeAccessor(BaseAccessor):
    """Data accessor for EventBridge operations with multi-region support."""

    MAX_RETRIES = 5

    @inject
    def __init__(
        self, logger: CliLogger, client_factory: Callable[[str, str], Any]
    ) -> None:
        super().__init__(logger, "EventBridge API")
        self.create_client = client_factory

    def _get_client(self, region: str) -> Any:
        """Get EventBridge client for specified region using cached factory."""
        return self.create_client(EVENTBRIDGE_SERVICE_NAME, region)

    @retry(exceptions=ClientError, tries=MAX_RETRIES, delay=1, backoff=2, logger=None)
    def list_rules(
        self,
        region: str,
        name_prefix: Optional[str] = None,
        event_bus_name: Optional[str] = None,
    ) -> ListRulesResponseTypeDef:
        """List EventBridge rules in specified region."""
        try:
            client = self._get_client(region)
            paginator = client.get_paginator("list_rules")
            kwargs = {}
            if name_prefix:
                kwargs["NamePrefix"] = name_prefix
            if event_bus_name:
                kwargs["EventBusName"] = event_bus_name

            rules = []
            for page in paginator.paginate(**kwargs):
                rules.extend(page.get("Rules", []))

            return cast(ListRulesResponseTypeDef, {"Rules": rules})
        except ClientError as exception:
            self._handle_error(exception, "list_rules")
            raise
        except Exception as exception:
            self.logger.error(f"Unexpected error in list_rules: {str(exception)}")
            raise

    @retry(exceptions=ClientError, tries=MAX_RETRIES, delay=1, backoff=2, logger=None)
    def describe_rule(
        self, region: str, name: str, event_bus_name: Optional[str] = None
    ) -> DescribeRuleResponseTypeDef:
        """Describe EventBridge rule in specified region."""
        try:
            client = self._get_client(region)
            kwargs = {"Name": name}
            if event_bus_name:
                kwargs["EventBusName"] = event_bus_name

            return cast(DescribeRuleResponseTypeDef, client.describe_rule(**kwargs))
        except ClientError as exception:
            self._handle_error(exception, "describe_rule")
            raise
        except Exception as exception:
            self.logger.error(f"Unexpected error in describe_rule: {str(exception)}")
            raise

    @retry(exceptions=ClientError, tries=MAX_RETRIES, delay=1, backoff=2, logger=None)
    def list_event_buses(
        self, region: str, name_prefix: Optional[str] = None
    ) -> ListEventBusesResponseTypeDef:
        """List EventBridge event buses in specified region."""
        try:
            client = self._get_client(region)
            kwargs = {}
            if name_prefix:
                kwargs["NamePrefix"] = name_prefix

            return cast(
                ListEventBusesResponseTypeDef, client.list_event_buses(**kwargs)
            )
        except ClientError as exception:
            self._handle_error(exception, "list_event_buses")
            raise
        except Exception as exception:
            self.logger.error(f"Unexpected error in list_event_buses: {str(exception)}")
            raise

    @retry(exceptions=ClientError, tries=MAX_RETRIES, delay=1, backoff=2, logger=None)
    def describe_event_bus(
        self, region: str, name: str
    ) -> DescribeEventBusResponseTypeDef:
        """Describe EventBridge event bus by name."""
        try:
            client = self._get_client(region)
            return cast(
                DescribeEventBusResponseTypeDef, client.describe_event_bus(Name=name)
            )
        except ClientError as exception:
            self._handle_error(exception, "describe_event_bus")
            raise
        except Exception as exception:
            self.logger.error(
                f"Unexpected error in describe_event_bus: {str(exception)}"
            )
            raise
