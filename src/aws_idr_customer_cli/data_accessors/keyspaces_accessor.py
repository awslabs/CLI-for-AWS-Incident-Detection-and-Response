from typing import Any, Callable, cast

from botocore.exceptions import ClientError
from injector import inject
from mypy_boto3_keyspaces.type_defs import GetKeyspaceResponseTypeDef
from retry import retry

from aws_idr_customer_cli.data_accessors.base_accessor import BaseAccessor
from aws_idr_customer_cli.utils.constants import BotoServiceName
from aws_idr_customer_cli.utils.log_handlers import CliLogger


class KeyspacesAccessor(BaseAccessor):
    """Data accessor for Keyspaces operations with multi-region support."""

    MAX_RETRIES = 5

    @inject
    def __init__(
        self, logger: CliLogger, client_factory: Callable[[str, str], Any]
    ) -> None:
        super().__init__(logger, "Keyspaces API")
        self.create_client = client_factory

    def _get_client(self, region: str) -> Any:
        """Get Keyspaces client for specified region using cached factory."""
        return self.create_client(BotoServiceName.KEYSPACES, region)

    @retry(exceptions=ClientError, tries=MAX_RETRIES, delay=1, backoff=2, logger=None)
    def get_keyspace(
        self, keyspace_name: str, region: str
    ) -> GetKeyspaceResponseTypeDef:
        """Get Keyspaces keyspace details."""
        try:
            client = self._get_client(region)
            return cast(
                GetKeyspaceResponseTypeDef,
                client.get_keyspace(keyspaceName=keyspace_name),
            )
        except ClientError as exception:
            self._handle_error(exception, "get_keyspace")
            raise
        except Exception as exception:
            self.logger.error(f"Unexpected error in get_keyspace: {str(exception)}")
            raise
