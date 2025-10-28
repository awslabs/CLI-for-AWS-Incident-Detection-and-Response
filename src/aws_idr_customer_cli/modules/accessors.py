from functools import lru_cache
from typing import Any

import boto3
from injector import Module, provider, singleton
from mypy_boto3_support import SupportClient

from aws_idr_customer_cli.data_accessors.alarm_accessor import AlarmAccessor
from aws_idr_customer_cli.data_accessors.resource_tagging_accessor import (
    ResourceTaggingAccessor,
)
from aws_idr_customer_cli.data_accessors.support_case_accessor import (
    SupportCaseAccessor,
)
from aws_idr_customer_cli.utils.log_handlers import CliLogger

SERVICE_REGION_FALLBACK_MAPPING = {
    "cloudwatch": "us-east-1",
}


@lru_cache
def create_aws_client(service: str, region: str) -> Any:
    """Universal cached AWS client factory."""
    if region == "global" and service in SERVICE_REGION_FALLBACK_MAPPING:
        region = SERVICE_REGION_FALLBACK_MAPPING[service]
    return boto3.client(service, region_name=region)  # type: ignore


class AccessorsModule(Module):
    """Module for providing AWS service accessors"""

    @singleton
    @provider
    def provide_resource_tagging_accessor(
        self, logger: CliLogger
    ) -> ResourceTaggingAccessor:
        """Provide AWS Resource Groups Tagging API accessor."""

        return ResourceTaggingAccessor(logger=logger, client_factory=create_aws_client)

    @singleton
    @provider
    def provide_alarm_accessor(self, logger: CliLogger) -> AlarmAccessor:
        """Provide AWS CloudWatch alarm accessor."""

        return AlarmAccessor(logger=logger, client_factory=create_aws_client)

    @singleton
    @provider
    def provide_support_accessor(
        self, logger: CliLogger, client: SupportClient
    ) -> SupportCaseAccessor:
        return SupportCaseAccessor(support_client=client, logger=logger)
