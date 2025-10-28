from typing import Any

from botocore.exceptions import ClientError

from aws_idr_customer_cli.exceptions import ValidationError
from aws_idr_customer_cli.utils.constants import Region
from aws_idr_customer_cli.utils.log_handlers import CliLogger


class BotoS3Manager:
    """Manager for S3 operations using boto3."""

    def __init__(self, s3_client: Any, logger: CliLogger):
        self._client = s3_client
        self._logger = logger

    def get_bucket_location(self, bucket_name: str) -> str:
        """Get S3 bucket region, handling us-east-1 special case."""
        try:
            response = self._client.get_bucket_location(Bucket=bucket_name)
            # AWS returns None for us-east-1 buckets
            return response.get("LocationConstraint") or str(Region.US_EAST_1.value)
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code in ("NoSuchBucket", "InvalidBucketName"):
                raise ValidationError(
                    f"S3 bucket '{bucket_name}' not found or invalid."
                )
            elif error_code in ("AccessDenied", "Forbidden"):
                raise ValidationError(f"Access denied to S3 bucket '{bucket_name}'.")
            else:
                raise ValidationError(
                    f"Error accessing S3 bucket '{bucket_name}': {error_code}"
                )
