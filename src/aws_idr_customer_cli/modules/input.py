from typing import Type, cast

from injector import Binder, Module, provider, singleton

from aws_idr_customer_cli.core.interactive.ui import InteractiveUI
from aws_idr_customer_cli.input.input_resource_discovery import (
    InputResourceDiscovery,
)
from aws_idr_customer_cli.interfaces.input_service import InputService
from aws_idr_customer_cli.services.input_module.input_service import ClickInputService
from aws_idr_customer_cli.services.input_module.resource_finder_service import (
    ResourceFinderService,
)
from aws_idr_customer_cli.utils.log_handlers import CliLogger
from aws_idr_customer_cli.utils.validation.validator import Validate


class InputModule(Module):
    """Module for user input handling services."""

    def configure(self, binder: Binder) -> None:
        # Bind the input service implementation to its interface
        binder.bind(
            cast(Type[InputService], InputService),
            to=self.provide_input_service,
            scope=singleton,
        )

    @provider
    @singleton
    def provide_input_service(self, logger: CliLogger) -> InputService:
        """Provide an instance of ClickInputService with required dependencies."""
        return ClickInputService(logger)

    @provider
    @singleton
    def provide_interactive_ui(self) -> InteractiveUI:
        """Provide InteractiveUI instance."""
        return InteractiveUI()

    @provider
    @singleton
    def provide_input_resource_discovery(
        self,
        ui: InteractiveUI,
        resource_finder_service: ResourceFinderService,
        validator: Validate,
    ) -> InputResourceDiscovery:
        """Provide resource discovery input handler."""
        return InputResourceDiscovery(
            ui=ui,
            resource_finder_service=resource_finder_service,
            validator=validator,
        )
