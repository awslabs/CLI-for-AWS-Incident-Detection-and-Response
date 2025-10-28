"""Helper functions for CloudFormation stack resource extraction and processing."""

from typing import Dict, Optional

from aws_idr_customer_cli.data_accessors.cloudformation_accessor import (
    CloudFormationAccessor,
)


def extract_stack_resources(
    stack_name: str,
    region: str,
    account_id: str,
    cloudformation_accessor: CloudFormationAccessor,
) -> Dict[str, Optional[str]]:
    """
    Extract webhook URL, secret name, and EventBus ARN from CloudFormation stack resources.
    """
    try:
        resources = cloudformation_accessor.get_stack_resources(
            stack_name=stack_name, region=region
        )

        api_id = None
        secret_name = None
        eventbus_arn = None

        for resource in resources:
            resource_type = resource.get("ResourceType", "")
            physical_id = resource.get("PhysicalResourceId", "")

            if "ApiGateway::RestApi" in resource_type:
                api_id = physical_id
            elif "SecretsManager::Secret" in resource_type and physical_id:
                secret_name = (
                    physical_id.split(":")[-1] if ":" in physical_id else physical_id
                )
            elif (
                "EventBridge::EventBus" in resource_type
                or "Events::EventBus" in resource_type
            ) and physical_id:
                eventbus_arn = _format_eventbus_arn(
                    physical_id=physical_id, region=region, account_id=account_id
                )

        webhook_url = None
        if api_id:
            webhook_url = _build_webhook_url(
                api_id=api_id, region=region, stack_name=stack_name
            )

        return {
            "webhook_url": webhook_url,
            "secret_name": secret_name,
            "eventbus_arn": eventbus_arn,
        }
    except Exception:
        return {"webhook_url": None, "secret_name": None, "eventbus_arn": None}


def _build_webhook_url(api_id: str, region: str, stack_name: str) -> str:
    """
    Build webhook URL from API Gateway components.

    """
    stage_name = f"{stack_name.replace('IDR-', '')}-Stage-Prod"
    return (
        f"https://{api_id}.execute-api.{region}"
        f".amazonaws.com/{stage_name}/APIGWResourcesforAPM"
    )


def _format_eventbus_arn(physical_id: str, region: str, account_id: str) -> str:
    """
    Format EventBus ARN from physical resource ID.

    """
    if physical_id.startswith("arn:"):
        return physical_id
    return f"arn:aws:events:{region}:{account_id}:event-bus/{physical_id}"
