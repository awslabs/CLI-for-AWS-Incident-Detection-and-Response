from typing import Any, Callable, List, cast

from botocore.exceptions import ClientError
from injector import inject
from mypy_boto3_rds.type_defs import DBInstanceTypeDef
from retry import retry

from aws_idr_customer_cli.data_accessors.base_accessor import BaseAccessor
from aws_idr_customer_cli.utils.constants import BotoServiceName
from aws_idr_customer_cli.utils.log_handlers import CliLogger


class RdsAccessor(BaseAccessor):
    """Data accessor for RDS operations with multi-region support."""

    MAX_RETRIES = 5

    @inject
    def __init__(
        self, logger: CliLogger, client_factory: Callable[[str, str], Any]
    ) -> None:
        super().__init__(logger, "RDS API")
        self.create_client = client_factory

    def _get_client(self, region: str) -> Any:
        """Get RDS client for specified region using cached factory."""
        return self.create_client(BotoServiceName.RDS, region)

    @retry(exceptions=ClientError, tries=MAX_RETRIES, delay=1, backoff=2, logger=None)
    def describe_db_instances(
        self, db_instance_identifier: str, region: str
    ) -> List[DBInstanceTypeDef]:
        """Describe RDS DB instances."""
        try:
            client = self._get_client(region)
            response = client.describe_db_instances(
                DBInstanceIdentifier=db_instance_identifier
            )
            return cast(List[DBInstanceTypeDef], response.get("DBInstances", []))
        except ClientError as exception:
            self._handle_error(exception, "describe_db_instances")
            raise
        except Exception as exception:
            self.logger.error(
                f"Unexpected error in describe_db_instances: {str(exception)}"
            )
            raise
