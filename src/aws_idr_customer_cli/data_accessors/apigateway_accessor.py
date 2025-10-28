from typing import Any, Callable, Optional

from injector import inject

from aws_idr_customer_cli.data_accessors.base_accessor import BaseAccessor
from aws_idr_customer_cli.utils.log_handlers import CliLogger


class ApiGatewayAccessor(BaseAccessor):

    @inject
    def __init__(
        self, logger: CliLogger, client_factory: Callable[[str, str], Any]
    ) -> None:
        super().__init__(logger, "API Gateway API")
        self.create_client = client_factory

    def get_rest_api_name(self, api_id: str, region: str) -> Optional[str]:
        try:
            self.logger.debug(
                f"Calling API Gateway GetRestApi API for API ID: {api_id} in region: {region}"
            )
            client = self.create_client("apigateway", region)
            response = client.get_rest_api(restApiId=api_id)
            name = response.get("name")

            if name is not None:
                return str(name)
            else:
                self.logger.warning(
                    f"API Gateway GetRestApi returned no 'name' field for API ID: {api_id}"
                )
                return None
        except Exception as e:
            self.logger.warning(
                f"Failed to call API Gateway GetRestApi for "
                f"API ID {api_id} in region {region}: {str(e)}"
            )
            return None
