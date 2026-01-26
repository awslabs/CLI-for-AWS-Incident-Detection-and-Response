from typing import Any, Callable, cast

from botocore.exceptions import ClientError
from injector import inject
from mypy_boto3_lambda.type_defs import FunctionConfigurationTypeDef
from retry import retry

from aws_idr_customer_cli.data_accessors.base_accessor import BaseAccessor
from aws_idr_customer_cli.utils.constants import BotoServiceName
from aws_idr_customer_cli.utils.log_handlers import CliLogger


class LambdaAccessor(BaseAccessor):
    """Data accessor for Lambda operations with multi-region support."""

    MAX_RETRIES = 5

    @inject
    def __init__(
        self, logger: CliLogger, client_factory: Callable[[str, str], Any]
    ) -> None:
        super().__init__(logger, "Lambda API")
        self.create_client = client_factory

    def _get_client(self, region: str) -> Any:
        """Get Lambda client for specified region using cached factory."""
        return self.create_client(BotoServiceName.LAMBDA, region)

    @retry(exceptions=ClientError, tries=MAX_RETRIES, delay=1, backoff=2, logger=None)
    def get_function_configuration(
        self, function_name: str, region: str
    ) -> FunctionConfigurationTypeDef:
        """Get Lambda function configuration."""
        try:
            client = self._get_client(region)
            return cast(
                FunctionConfigurationTypeDef,
                client.get_function_configuration(FunctionName=function_name),
            )
        except ClientError as exception:
            self._handle_error(exception, "get_function_configuration")
            raise
        except Exception as exception:
            self.logger.error(
                f"Unexpected error in get_function_configuration: {str(exception)}"
            )
            raise
