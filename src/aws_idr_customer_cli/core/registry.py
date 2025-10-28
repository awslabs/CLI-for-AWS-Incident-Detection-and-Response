import importlib.metadata
import importlib.util
import inspect
from pathlib import Path
from typing import Any, Dict, Optional, TypedDict

import click
from injector import Injector

from aws_idr_customer_cli.modules.logging import LoggingModule
from aws_idr_customer_cli.utils.log_handlers import CliLogger

COMMAND_FILE = "command.py"
COMMAND_PACKAGE = "aws_idr_customer_cli.commands"
IGNORE_PREFIX = "_"
COMMAND_ATTR = "execute"
NAME_ATTR = "name"


class CliContext(TypedDict):
    verbose: bool
    debug: bool


class CommandRegistry:
    """Registry with automatic command discovery."""

    def __init__(self, injector: Injector, logger: CliLogger):
        self.injector = injector
        self.logger = logger
        self.commands: Dict[str, click.Command] = {}

    def discover_commands(self, commands_dir: Optional[str] = None) -> None:
        """
        Automatically discover and register CLI commands.

        Looks for command.py files in subdirectories and loads any classes
        that use the @command decorator. For example, if it finds:
        commands/alarm/command.py with @command("create_alarm"), it will
        register it as a CLI command that can be run as 'create_alarm'.

        Commands must follow the pattern:
        @command("create_alarm")
        class CreateAlarm(CommandBase):
            def execute(self, **kwargs):
                pass

        Dynamic loading process:
        1. Converts path to module: commands/alarm/create/command.py →
           aws_idr_customer_cli.commands.alarm.create.command
        2. Loads module and finds command classes
        3. Registers commands with dependency injection

        Args:
            commands_dir: Optional custom path for commands directory
        """
        if commands_dir is None:
            commands_dir = str(Path(__file__).parent.parent / "commands")

        base_path = Path(commands_dir)
        if not base_path.exists():
            self.logger.error(f"Commands directory not found: {base_path}")
            return

        for command_dir in base_path.glob("**/"):
            if command_dir.name.startswith(IGNORE_PREFIX):
                continue

            command_file = command_dir / COMMAND_FILE
            if not command_file.exists():
                continue

            try:
                # Import module
                module_name = (
                    f"{COMMAND_PACKAGE}.{command_dir.relative_to(base_path)}."
                    f"{COMMAND_FILE.replace('.py', '')}"
                )

                module_name = module_name.replace("/", ".").replace("\\", ".")

                spec = importlib.util.spec_from_file_location(module_name, command_file)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    # Find and register commands
                    for _, obj in inspect.getmembers(module):
                        if (
                            inspect.isclass(obj)
                            and hasattr(obj, COMMAND_ATTR)
                            and hasattr(getattr(obj, COMMAND_ATTR), NAME_ATTR)
                        ):
                            try:
                                cmd_instance = self.injector.get(obj)
                                cmd_name = getattr(obj.execute, NAME_ATTR)
                                self.commands[cmd_name] = cmd_instance.execute
                                self.logger.info(f"Discovered command: {cmd_name}")
                            except Exception as e:
                                self.logger.error(
                                    f"Failed to register command {obj.__name__}: {e}"
                                )

            except Exception as e:
                self.logger.error(f"Error loading commands from {command_file}: {e}")

    def create_cli(self) -> click.Group:
        """Create the CLI group with all discovered commands."""

        cli_group = click.Group()

        # Add global options to the CLI group
        cli_group = click.option(
            "--verbose", "-v", is_flag=True, help="Enable verbose output"
        )(cli_group)
        cli_group = click.option("--debug", is_flag=True, help="Enable debug mode")(
            cli_group
        )
        try:
            version = importlib.metadata.version("awsidr")
        except importlib.metadata.PackageNotFoundError:
            version = importlib.metadata.version("amzn-idr-cli")
        cli_group = click.version_option(version=version, message="%(version)s")(
            cli_group
        )

        # Override the callback to handle global options
        original_callback = cli_group.callback

        @click.pass_context
        def global_options_callback(
            ctx: click.Context,
            verbose: bool = False,
            debug: bool = False,
            **kwargs: Any,
        ) -> Any:
            """Handle global options."""
            # Configure logging based on global flags
            LoggingModule.configure_console_logging(
                injector=self.injector, verbose=verbose, debug=debug, logger=self.logger
            )

            # Store options in context for access by subcommands
            ctx.ensure_object(dict)
            ctx.obj.update(
                {
                    "injector": self.injector,
                    "verbose": verbose,
                    "debug": debug,
                }
            )

            # Call original callback if exists
            if original_callback:
                return original_callback(ctx, **kwargs)

        cli_group.callback = global_options_callback

        # Add discovered commands
        for command_func in self.commands.values():
            cli_group.add_command(command_func)

        return cli_group
