from typing import Any, Callable, cast

from botocore.exceptions import ClientError
from injector import inject
from mypy_boto3_dynamodb.type_defs import TableDescriptionTypeDef
from retry import retry

from aws_idr_customer_cli.data_accessors.base_accessor import BaseAccessor
from aws_idr_customer_cli.utils.constants import BotoServiceName
from aws_idr_customer_cli.utils.log_handlers import CliLogger


class DynamoDbAccessor(BaseAccessor):
    """Data accessor for DynamoDB operations with multi-region support."""

    MAX_RETRIES = 5

    @inject
    def __init__(
        self, logger: CliLogger, client_factory: Callable[[str, str], Any]
    ) -> None:
        super().__init__(logger, "DynamoDB API")
        self.create_client = client_factory

    def _get_client(self, region: str) -> Any:
        """Get DynamoDB client for specified region using cached factory."""
        return self.create_client(BotoServiceName.DYNAMODB, region)

    @retry(exceptions=ClientError, tries=MAX_RETRIES, delay=1, backoff=2, logger=None)
    def describe_table(self, table_name: str, region: str) -> TableDescriptionTypeDef:
        """Describe DynamoDB table."""
        try:
            client = self._get_client(region)
            response = client.describe_table(TableName=table_name)
            return cast(TableDescriptionTypeDef, response.get("Table", {}))
        except ClientError as exception:
            self._handle_error(exception, "describe_table")
            raise
        except Exception as exception:
            self.logger.error(f"Unexpected error in describe_table: {str(exception)}")
            raise
