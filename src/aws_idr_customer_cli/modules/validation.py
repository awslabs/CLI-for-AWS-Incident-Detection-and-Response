from injector import Binder, Module, provider, singleton

from aws_idr_customer_cli.clients.ec2 import BotoEc2Manager
from aws_idr_customer_cli.utils.validation.validator import Validate
from aws_idr_customer_cli.utils.validation.workload_validation import WorkloadValidate


class ValidationModule(Module):
    """Validation services module - simplified."""

    def configure(self, binder: Binder) -> None:
        binder.bind(WorkloadValidate, scope=singleton)

    @singleton
    @provider
    def provide_validator(self, ec2_manager: BotoEc2Manager) -> Validate:
        """Provide Validator."""

        return Validate(ec2_manager=ec2_manager)
