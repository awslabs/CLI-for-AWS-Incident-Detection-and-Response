from typing import Any, Callable, Dict, List, Optional, cast

from botocore.exceptions import ClientError, WaiterError
from injector import inject
from mypy_boto3_cloudformation.type_defs import (
    CreateStackOutputTypeDef,
    DescribeStacksOutputTypeDef,
    ListStacksOutputTypeDef,
    ValidateTemplateOutputTypeDef,
)
from retry import retry

from aws_idr_customer_cli.data_accessors.base_accessor import BaseAccessor
from aws_idr_customer_cli.utils.apm.apm_constants import (
    STACK_DEPLOYMENT_TIMEOUT,
    STACK_POLL_INTERVAL,
    StackStatus,
)
from aws_idr_customer_cli.utils.log_handlers import CliLogger

CLOUDFORMATION_SERVICE_NAME = "cloudformation"

ACTIVE_STACK_STATUSES = [
    "CREATE_IN_PROGRESS",
    "CREATE_COMPLETE",
    "ROLLBACK_IN_PROGRESS",
    "ROLLBACK_COMPLETE",
    "UPDATE_IN_PROGRESS",
    "UPDATE_COMPLETE",
    "UPDATE_ROLLBACK_IN_PROGRESS",
    "UPDATE_ROLLBACK_COMPLETE",
    "REVIEW_IN_PROGRESS",
    "IMPORT_IN_PROGRESS",
    "IMPORT_COMPLETE",
]

DELETED_STACK_STATUS = "DELETE_COMPLETE"


class CloudFormationAccessor(BaseAccessor):
    """Data accessor for CloudFormation operations with multi-region support."""

    MAX_RETRIES = 5

    @inject
    def __init__(
        self, logger: CliLogger, client_factory: Callable[[str, str], Any]
    ) -> None:
        super().__init__(logger, "CloudFormation API")
        self.create_client = client_factory

    def _get_client(self, region: str) -> Any:
        """Get CloudFormation client for specified region using cached factory."""
        return self.create_client(CLOUDFORMATION_SERVICE_NAME, region)

    @retry(exceptions=ClientError, tries=MAX_RETRIES, delay=1, backoff=2, logger=None)
    def list_stacks(
        self, region: str, stack_status_filter: Optional[List[str]] = None
    ) -> ListStacksOutputTypeDef:
        """List CloudFormation stacks in specified region."""
        try:
            client = self._get_client(region=region)
            paginator = client.get_paginator("list_stacks")
            kwargs = {}
            if stack_status_filter:
                kwargs["StackStatusFilter"] = stack_status_filter

            stacks = []
            for page in paginator.paginate(**kwargs):
                stacks.extend(page.get("StackSummaries", []))

            return cast(ListStacksOutputTypeDef, {"StackSummaries": stacks})
        except ClientError as exception:
            self._handle_error(exception, "list_stacks")
            raise

    @retry(exceptions=ClientError, tries=MAX_RETRIES, delay=1, backoff=2, logger=None)
    def stack_exists(
        self, stack_name: str, region: str, exclude_deleted: bool = True
    ) -> bool:
        """Check if a CloudFormation stack exists"""
        try:
            response = self.describe_stacks(region=region, stack_name=stack_name)
            stacks = response.get("Stacks", [])

            if not stacks:
                return False

            stack = stacks[0]
            status = stack.get("StackStatus", "")

            if exclude_deleted and status == DELETED_STACK_STATUS:
                return False

            return True

        except (ClientError, ValueError) as exception:
            error_code = (
                getattr(exception, "response", {}).get("Error", {}).get("Code", "")
            )
            if error_code == "ValidationError" or "ValidationError" in str(exception):
                return False
            raise

    @retry(exceptions=ClientError, tries=MAX_RETRIES, delay=1, backoff=2, logger=None)
    def deploy_stack(
        self,
        region: str,
        stack_name: str,
        template_body: Optional[str] = None,
        template_url: Optional[str] = None,
        parameters: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> CreateStackOutputTypeDef:
        """Deploy CloudFormation stack with parameters for APM integration."""
        if not template_body and not template_url:
            raise ValueError("Either template_body or template_url must be provided")
        if template_body and template_url:
            raise ValueError("Cannot specify both template_body and template_url")

        try:
            client = self._get_client(region=region)
            create_params = {"StackName": stack_name, **kwargs}

            if template_body:
                create_params["TemplateBody"] = template_body
            else:
                create_params["TemplateURL"] = template_url

            if parameters:
                param_list = [
                    {"ParameterKey": k, "ParameterValue": v}
                    for k, v in parameters.items()
                ]
                create_params["Parameters"] = param_list

            if "Capabilities" not in create_params:
                create_params["Capabilities"] = [
                    "CAPABILITY_IAM",
                    "CAPABILITY_NAMED_IAM",
                ]

            return cast(CreateStackOutputTypeDef, client.create_stack(**create_params))
        except ClientError as exception:
            self._handle_error(exception, "deploy_stack")
            raise

    @retry(exceptions=ClientError, tries=MAX_RETRIES, delay=1, backoff=2, logger=None)
    def describe_stacks(
        self, region: str, stack_name: Optional[str] = None
    ) -> DescribeStacksOutputTypeDef:
        """Describe CloudFormation stacks in specified region."""
        try:
            client = self._get_client(region=region)
            if stack_name:
                return cast(
                    DescribeStacksOutputTypeDef,
                    client.describe_stacks(StackName=stack_name),
                )
            else:
                paginator = client.get_paginator("describe_stacks")
                stacks = []
                for page in paginator.paginate():
                    stacks.extend(page.get("Stacks", []))
                return cast(DescribeStacksOutputTypeDef, {"Stacks": stacks})
        except ClientError as exception:
            self._handle_error(exception, "describe_stacks")
            raise

    @retry(exceptions=ClientError, tries=MAX_RETRIES, delay=1, backoff=2, logger=None)
    def wait_for_stack_create(
        self, stack_name: str, region: str, timeout: int = STACK_DEPLOYMENT_TIMEOUT
    ) -> Dict[str, Any]:
        """Wait for stack deployment to complete with timeout."""
        try:
            client = self._get_client(region=region)

            waiter = client.get_waiter("stack_create_complete")
            waiter.wait(
                StackName=stack_name,
                WaiterConfig={
                    "Delay": STACK_POLL_INTERVAL,
                    "MaxAttempts": timeout // STACK_POLL_INTERVAL,
                },
            )

            response = client.describe_stacks(StackName=stack_name)
            stack = response["Stacks"][0]

            self.logger.info(f"Stack {stack_name} created successfully")
            return {
                "Status": stack["StackStatus"],
                "Success": True,
                "StackId": stack.get("StackId", ""),
                "Reason": None,
            }

        except WaiterError:
            try:
                response = client.describe_stacks(StackName=stack_name)
                stack = response["Stacks"][0]
                status = stack["StackStatus"]
                reason = stack.get("StackStatusReason", "Unknown failure reason")
            except ClientError:
                status = StackStatus.TIMEOUT.value
                reason = f"Deployment timeout after {timeout} seconds"

            self.logger.error(f"Stack {stack_name} failed: {reason}")
            return {
                "Status": status,
                "Success": False,
                "StackId": None,
                "Reason": reason,
            }
        except ClientError as exception:
            self._handle_error(exception, "wait_for_stack_create")
            raise

    @retry(exceptions=ClientError, tries=MAX_RETRIES, delay=1, backoff=2, logger=None)
    def validate_template(
        self,
        region: str,
        template_body: Optional[str] = None,
        template_url: Optional[str] = None,
    ) -> ValidateTemplateOutputTypeDef:
        """Validate CloudFormation template."""
        if not template_body and not template_url:
            raise ValueError("Either template_body or template_url must be provided")
        if template_body and template_url:
            raise ValueError("Cannot specify both template_body and template_url")

        try:
            client = self._get_client(region=region)
            params = {}
            if template_body:
                params["TemplateBody"] = template_body
            elif template_url:
                params["TemplateURL"] = template_url

            return cast(
                ValidateTemplateOutputTypeDef, client.validate_template(**params)
            )
        except ClientError as exception:
            self._handle_error(exception, "validate_template")
            raise

    @retry(exceptions=ClientError, tries=MAX_RETRIES, delay=1, backoff=2, logger=None)
    def get_stack_resources(self, stack_name: str, region: str) -> List[Dict[str, Any]]:
        """Get all resources created by the stack."""
        try:
            client = self._get_client(region=region)
            response = client.list_stack_resources(StackName=stack_name)
            return cast(
                List[Dict[str, Any]], response.get("StackResourceSummaries", [])
            )
        except ClientError as exception:
            if exception.response["Error"]["Code"] == "ValidationError":
                return []
            self._handle_error(exception, "get_stack_resources")
            raise

    @retry(exceptions=ClientError, tries=MAX_RETRIES, delay=1, backoff=2, logger=None)
    def delete_stack(self, stack_name: str, region: str) -> Dict[str, str]:
        """Delete CloudFormation stack and wait for completion."""
        try:
            client = self._get_client(region=region)
            client.delete_stack(StackName=stack_name)

            waiter = client.get_waiter("stack_delete_complete")
            waiter.wait(StackName=stack_name)

            return {
                "StackName": stack_name,
                "Region": region,
                "Status": "DELETE_COMPLETE",
            }
        except ClientError as exception:
            if exception.response["Error"]["Code"] == "ValidationError":
                return {
                    "StackName": stack_name,
                    "Region": region,
                    "Status": "NOT_FOUND",
                }
            raise

    @retry(exceptions=ClientError, tries=MAX_RETRIES, delay=1, backoff=2, logger=None)
    def get_stack_events(self, stack_name: str, region: str) -> List[Dict[str, Any]]:
        """Get stack events to identify failure reasons."""
        try:
            client = self._get_client(region=region)
            response = client.describe_stack_events(StackName=stack_name)
            return cast(List[Dict[str, Any]], response.get("StackEvents", []))
        except ClientError as exception:
            self._handle_error(exception, "get_stack_events")
            raise

    @retry(exceptions=ClientError, tries=MAX_RETRIES, delay=1, backoff=2, logger=None)
    def update_termination_protection(
        self, stack_name: str, region: str, enable: bool
    ) -> None:
        """Update termination protection for a CloudFormation stack."""
        try:
            client = self._get_client(region=region)
            client.update_termination_protection(
                StackName=stack_name, EnableTerminationProtection=enable
            )
            status = "enabled" if enable else "disabled"
            self.logger.info(f"Termination protection {status} for stack {stack_name}")
        except ClientError as exception:
            self._handle_error(exception, "update_termination_protection")
            raise
