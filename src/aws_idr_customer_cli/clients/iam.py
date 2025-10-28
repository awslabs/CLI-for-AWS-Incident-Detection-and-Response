from botocore.exceptions import ClientError
from mypy_boto3_iam import IAMClient

from aws_idr_customer_cli.utils.log_handlers import CliLogger


class BotoIamManager:
    def __init__(self, iam_client: IAMClient, logger: CliLogger):
        self._client = iam_client
        self._logger = logger

    def service_linked_role_exists(self, role_name: str) -> bool:
        try:
            self._client.get_role(RoleName=role_name)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchEntity":
                return False
            raise

    def create_service_linked_role(self, service_name: str) -> str:
        try:
            response = self._client.create_service_linked_role(
                AWSServiceName=service_name
            )
            role_name: str = response["Role"]["RoleName"]
            return role_name
        except ClientError as e:
            if e.response["Error"]["Code"] == "InvalidInput":
                raise ValueError(
                    f"Service {service_name} does not support service-linked roles"
                )
            raise
