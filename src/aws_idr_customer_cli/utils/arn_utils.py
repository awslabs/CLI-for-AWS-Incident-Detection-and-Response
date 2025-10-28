from arnparse import arnparse

from aws_idr_customer_cli.services.file_cache.data import ResourceArn


def extract_account_id_from_arn(resource_arn: str) -> str:
    """
    Extract AWS account ID from ARN.

    Args:
        resource_arn: ARN string

    Returns:
        Account ID string
    """
    arn = arnparse(resource_arn)
    if not arn.account_id:
        raise ValueError(f"No account ID found in ARN: {resource_arn}")
    return str(arn.account_id)


def extract_resource_id_from_arn(resource_arn: str) -> str:
    """
    Extract resource ID from ARN.

    Always returns the last part after the final slash, which is typically the unique resource ID.

    Examples:
        - EC2: arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0 → i-1234567890abcdef0
        - S3: arn:aws:s3:::my-bucket → my-bucket
        - ELB: arn:aws:elasticloadbalancing:us-west-2:123456789012:loadbalancer/app/my-lb/123 → 123

    Args:
        resource_arn: ARN string

    Returns:
        Resource ID string
    """
    arn = arnparse(resource_arn)
    if not arn.resource:
        raise ValueError(f"No resource found in ARN: {resource_arn}")

    resource = arn.resource
    if "/" in resource:
        return str(resource.split("/")[-1])
    else:
        return str(resource)


def build_resource_arn_object(resource_arn: str) -> ResourceArn:
    """
    Convert resource arn string to ResourceArn object.

    ARN Format: arn:partition:service:region:account-id:resource-id
    Examples:
      - EC2: arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0
      - S3: arn:aws:s3:::my-bucket
      - ELB: arn:aws:elasticloadbalancing:us-west-2:123456789012:
             loadbalancer/app/my-lb/50dc6c495c0c9188

    Args:
        resource_arn: str

    Returns:
        ResourceArn object
    """
    arn = arnparse(resource_arn)
    return ResourceArn(
        type=(
            arn.service + ":" + arn.resource_type if arn.resource_type else arn.service
        ),
        arn=resource_arn,
        region=arn.region if arn.region else "global",
    )
