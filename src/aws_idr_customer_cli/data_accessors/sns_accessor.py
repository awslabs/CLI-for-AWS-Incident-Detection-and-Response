from typing import Any, Callable, cast

from botocore.exceptions import ClientError
from injector import inject
from mypy_boto3_sns.type_defs import (
    GetTopicAttributesResponseTypeDef,
    ListTopicsResponseTypeDef,
)
from retry import retry

from aws_idr_customer_cli.data_accessors.base_accessor import BaseAccessor
from aws_idr_customer_cli.utils.log_handlers import CliLogger

SNS_SERVICE_NAME = "sns"


class SnsAccessor(BaseAccessor):
    """Data accessor for SNS operations with multi-region support."""

    MAX_RETRIES = 5

    @inject
    def __init__(
        self, logger: CliLogger, client_factory: Callable[[str, str], Any]
    ) -> None:
        super().__init__(logger, "SNS API")
        self.create_client = client_factory

    def _get_client(self, region: str) -> Any:
        """Get SNS client for specified region using cached factory."""
        return self.create_client(SNS_SERVICE_NAME, region)

    @retry(exceptions=ClientError, tries=MAX_RETRIES, delay=1, backoff=2, logger=None)
    def list_topics(self, region: str) -> ListTopicsResponseTypeDef:
        """List SNS topics in specified region."""
        try:
            client = self._get_client(region)
            paginator = client.get_paginator("list_topics")

            topics = []
            for page in paginator.paginate():
                topics.extend(page.get("Topics", []))

            return cast(ListTopicsResponseTypeDef, {"Topics": topics})
        except ClientError as exception:
            self._handle_error(exception, "list_topics")
            raise
        except Exception as exception:
            self.logger.error(f"Unexpected error in list_topics: {str(exception)}")
            raise

    @retry(exceptions=ClientError, tries=MAX_RETRIES, delay=1, backoff=2, logger=None)
    def get_topic_attributes(
        self, region: str, topic_arn: str
    ) -> GetTopicAttributesResponseTypeDef:
        """Get SNS topic attributes in specified region."""
        try:
            client = self._get_client(region)
            return cast(
                GetTopicAttributesResponseTypeDef,
                client.get_topic_attributes(TopicArn=topic_arn),
            )
        except ClientError as exception:
            self._handle_error(exception, "get_topic_attributes")
            raise
        except Exception as exception:
            self.logger.error(
                f"Unexpected error in get_topic_attributes: {str(exception)}"
            )
            raise
