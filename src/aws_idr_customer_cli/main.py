import click
from injector import Injector

from aws_idr_customer_cli.core.registry import CommandRegistry
from aws_idr_customer_cli.modules.injector_config import AppModule
from aws_idr_customer_cli.utils.log_handlers import CliLogger


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


def main() -> None:
    CLI().run()


if __name__ == "__main__":
    main()
