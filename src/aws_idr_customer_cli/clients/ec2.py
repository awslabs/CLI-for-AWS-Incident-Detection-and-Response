from typing import List

from botocore.exceptions import ClientError
from mypy_boto3_ec2 import EC2Client

from aws_idr_customer_cli.exceptions import ValidationError
from aws_idr_customer_cli.utils.log_handlers import CliLogger


class BotoEc2Manager:
    """Manager for retrieving AWS regions using boto3 operations."""

    def __init__(self, ec2_client: EC2Client, logger: CliLogger):
        self._client = ec2_client
        self._logger = logger

    def get_available_regions(self) -> List[str]:
        """Get available AWS regions using boto3 session."""
        try:
            response = self._client.describe_regions()
            regions: List[str] = [
                region["RegionName"] for region in response["Regions"]
            ]
            return regions
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code in (
                "RequestExpired",
                "ExpiredToken",
                "ExpiredTokenException",
            ):
                raise ValidationError("Your AWS credentials have expired.")
            elif error_code in ("UnauthorizedOperation", "AccessDenied"):
                raise ValidationError(
                    "AWS credentials missing or insufficient permissions."
                )
            elif error_code in ("InvalidUserID.NotFound", "SignatureDoesNotMatch"):
                raise ValidationError("Invalid AWS credentials.")
            else:
                raise ValidationError("AWS credentials issue or service unavailable.")
        except Exception as e:
            raise ValidationError(f"AWS credentials missing or invalid. {str(e)}")
