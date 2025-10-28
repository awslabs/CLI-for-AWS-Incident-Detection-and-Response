from injector import Module, provider, singleton

from aws_idr_customer_cli.core.interactive.ui import InteractiveUI
from aws_idr_customer_cli.utils.log_handlers import CliLogger
from aws_idr_customer_cli.utils.telemetry.cli_command_tracker import CliCommandTracker
from aws_idr_customer_cli.utils.telemetry_service import Telemetry


class BaseModule(Module):
    """Core application services."""

    @singleton
    @provider
    def provide_telemetry_service(self, logger: CliLogger) -> Telemetry:
        """Provide telemetry service with logger."""
        return Telemetry(logger=logger)

    @singleton
    @provider
    def provide_cli_command_tracker(
        self, telemetry: Telemetry, logger: CliLogger
    ) -> CliCommandTracker:
        """Provide CLI command tracking."""
        return CliCommandTracker(telemetry=telemetry, logger=logger)

    @singleton
    @provider
    def provide_interactive_ui(self) -> InteractiveUI:
        """Provide Interactive UI singleton."""
        return InteractiveUI()
