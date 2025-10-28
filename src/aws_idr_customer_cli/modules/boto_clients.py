import boto3
import injector
from mypy_boto3_support import SupportClient

from aws_idr_customer_cli.clients.ec2 import BotoEc2Manager
from aws_idr_customer_cli.clients.iam import BotoIamManager
from aws_idr_customer_cli.clients.s3 import BotoS3Manager
from aws_idr_customer_cli.clients.sts import BotoStsManager
from aws_idr_customer_cli.utils.log_handlers import CliLogger

US_EAST_1 = "us-east-1"


class BotoClientsModule(injector.Module):

    @injector.singleton
    @injector.provider
    def provide_boto_sts_client(self, logger: CliLogger) -> BotoStsManager:
        sts_client = boto3.client("sts")

        return BotoStsManager(sts_client=sts_client, logger=logger)

    @injector.singleton
    @injector.provider
    def provide_boto_ec2_client(self, logger: CliLogger) -> BotoEc2Manager:
        ec2_client = boto3.client("ec2", US_EAST_1)

        return BotoEc2Manager(ec2_client=ec2_client, logger=logger)

    @injector.singleton
    @injector.provider
    def provide_boto_support_client(self) -> SupportClient:
        support_client = boto3.client("support")
        return support_client

    @injector.singleton
    @injector.provider
    def provide_boto_iam_client(self, logger: CliLogger) -> BotoIamManager:
        iam_client = boto3.client("iam")
        return BotoIamManager(iam_client=iam_client, logger=logger)

    @injector.singleton
    @injector.provider
    def provide_boto_s3_client(self, logger: CliLogger) -> BotoS3Manager:
        s3_client = boto3.client("s3", US_EAST_1)
        return BotoS3Manager(s3_client=s3_client, logger=logger)
