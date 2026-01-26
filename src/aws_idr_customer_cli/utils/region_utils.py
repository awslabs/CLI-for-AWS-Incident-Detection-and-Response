"""Utilities for working with AWS regions."""

from functools import lru_cache
from typing import List

import boto3

from aws_idr_customer_cli.clients.ec2 import BotoEc2Manager
from aws_idr_customer_cli.utils.log_handlers import CliLogger

US_EAST_1 = "us-east-1"


@lru_cache(maxsize=1)
def get_valid_regions() -> List[str]:
    """
    Get all available AWS regions, cached for process lifetime.

    This function creates a BotoEc2Manager instance internally to fetch
    regions using the existing error handling logic. Results are cached
    so the AWS API is only called once per CLI process execution.

    Used for:
    - Region validation in user inputs
    - Lambda@Edge metric scanning across regions
    - Any feature requiring dynamic region discovery

    Returns:
        List of AWS region names (e.g., ['us-east-1', 'us-west-2', ...])

    Raises:
        ValidationError: If unable to fetch regions due to credential issues

    Example:
        >>> regions = get_valid_regions()
        >>> print(regions)
        ['us-east-1', 'us-west-2', 'eu-west-1', ...]
    """
    # Create minimal logger (won't spam console, just for error handling)
    logger = CliLogger("region_utils")

    # Create EC2 client for describe_regions API call
    ec2_client = boto3.client("ec2", region_name=US_EAST_1)

    # Use BotoEc2Manager for proper error handling
    ec2_manager = BotoEc2Manager(ec2_client, logger)

    # Fetch and return regions (error handling in BotoEc2Manager)
    regions: List[str] = ec2_manager.get_available_regions()
    return regions
