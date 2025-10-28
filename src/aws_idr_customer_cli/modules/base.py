from injector import Module, provider, singleton

from aws_idr_customer_cli.core.interactive.ui import InteractiveUI


class BaseModule(Module):
    """Core application services."""

    @singleton
    @provider
    def provide_interactive_ui(self) -> InteractiveUI:
        """Provide Interactive UI singleton."""
        return InteractiveUI()
