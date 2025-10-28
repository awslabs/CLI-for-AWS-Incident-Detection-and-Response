import re
from typing import Any, List

from injector import inject

from aws_idr_customer_cli.clients.ec2 import BotoEc2Manager
from aws_idr_customer_cli.exceptions import ValidationError
from aws_idr_customer_cli.utils.validation.validator import Validate


class WorkloadValidate:
    """Workload-specific validation functions."""

    @inject
    def __init__(self, ec2_manager: BotoEc2Manager):
        self._validator = Validate(ec2_manager)

    @staticmethod
    def workload_name(value: Any) -> str:
        """
        Validate workload name: 3-50 chars, alphanumeric + hyphens, trim whitespace.
        """
        if not isinstance(value, str):
            raise ValidationError("Workload name must be text")

        clean = value.strip()

        if len(clean) < 3:
            raise ValidationError("Workload name must be at least 3 characters")
        if len(clean) > 50:
            raise ValidationError("Workload name must be less than 50 characters")

        if not re.match(r"^[a-zA-Z0-9- ]+$", clean):
            raise ValidationError(
                "Workload name can only contain letters, numbers, hyphens, and spaces"
            )

        return clean


# Workload-specific validator functions
def validate_workload_name(value: Any) -> str:
    """Validate workload name with chaining."""
    result = Validate.chain(value, Validate.required, WorkloadValidate.workload_name)
    return str(result)


def validate_workload_regions(value: Any) -> List[str]:
    """Validate workload regions with chaining."""
    # Get WorkloadValidate instance from injector
    from injector import Injector

    from aws_idr_customer_cli.modules.injector_config import AppModule

    injector_instance = Injector([AppModule()])
    workload_validator = injector_instance.get(WorkloadValidate)

    result = Validate.chain(
        value, Validate.required, workload_validator._validator.aws_regions
    )
    return list(result)  # type: ignore
