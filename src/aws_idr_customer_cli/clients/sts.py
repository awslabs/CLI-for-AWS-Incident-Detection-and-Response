from botocore.exceptions import ClientError
from mypy_boto3_sts import STSClient

from aws_idr_customer_cli.exceptions import AccountIdError
from aws_idr_customer_cli.utils.log_handlers import CliLogger


class BotoStsManager:

    def __init__(self, sts_client: STSClient, logger: CliLogger):
        self._client = sts_client
        self._logger = logger

    def retrieve_account_id_from_sts(self) -> str:
        try:
            account_id: str = self._client.get_caller_identity()["Account"]
        except ClientError as e:
            if e.response["Error"]["Code"] == "ExpiredTokenException":
                self._logger.error(
                    "Unable to retrieve Account ID because AWS credentials have expired. \
                    Try to restart CloudShell session or renew your AWS credentials."
                )
            else:
                self._logger.error(
                    "Unable to retrieve Account ID. \
                    Try to restart CloudShell session or renew your AWS credentials."
                )
            raise AccountIdError
        return account_id
