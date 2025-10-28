import click
from injector import Injector

from aws_idr_customer_cli.core.registry import CommandRegistry
from aws_idr_customer_cli.modules.injector_config import AppModule
from aws_idr_customer_cli.utils.log_handlers import CliLogger
from aws_idr_customer_cli.utils.telemetry_service import Telemetry


class CLI:
    def __init__(self) -> None:
        # Set up dependency injection
        self.injector = Injector([AppModule()])
        self.logger = self.injector.get(CliLogger)

    def run(self) -> None:
        try:
            # Create and configure CLI
            registry = CommandRegistry(self.injector, self.logger)
            registry.discover_commands()
            cli = registry.create_cli()

            # Run CLI with injector in context
            cli(obj={"injector": self.injector})  # [1]

        except Exception as e:
            # Display error to user
            click.secho(f"Error: {str(e)}", fg="red", err=True)

            # Try to record unhandled exceptions
            try:
                self.injector.get(Telemetry).record_error(e)
            except Exception as telemetry_error:
                self.logger.error(
                    f"Failed to record error telemetry: {telemetry_error}"
                )
        finally:
            # Restore original error handling
            if hasattr(self.logger, "buffer_handler"):
                self.logger.buffer_handler.print_summary(self.logger)
            else:
                self.logger.error("Warning: No buffer handler found!")


def main() -> None:
    CLI().run()


if __name__ == "__main__":
    main()
