from typing import Any, List, Optional, Set, cast

import click
from injector import inject

from aws_idr_customer_cli.utils.log_handlers import CliLogger
from aws_idr_customer_cli.utils.telemetry.constants import ErrorOrigin, ErrorType
from aws_idr_customer_cli.utils.telemetry_service import Telemetry


class TelemetryEnabledGroup(click.Group):
    """
    Custom Click Group that captures command errors at the framework level.

    This directly extends Click's Group class to intercept errors before
    they're raised, ensuring we can track invalid commands and other
    framework-level errors.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the telemetry-enabled group."""
        self.telemetry: Optional[Telemetry] = None
        self.logger: Optional[CliLogger] = None
        self.valid_commands: Set[str] = set()
        super().__init__(*args, **kwargs)

    def set_services(self, telemetry: Telemetry, logger: CliLogger) -> None:
        """Set required services for telemetry tracking."""
        self.telemetry = telemetry
        self.logger = logger

    def add_command(self, cmd: click.Command, name: Optional[str] = None) -> None:
        """
        Track valid command names when they're added.

        Args:
            cmd: The Click command to add
            name: Optional override name
        """
        name = name or cmd.name
        if name:
            self.valid_commands.add(name)
        super().add_command(cmd, name)

    def get_command(self, ctx: click.Context, cmd_name: str) -> Optional[click.Command]:
        """
        Intercept command lookup to catch invalid commands.

        This is called by Click before executing a command, so we can
        track invalid command attempts here.

        Args:
            ctx: The Click context
            cmd_name: The command name being looked up

        Returns:
            The command if found, None otherwise
        """
        cmd = super().get_command(ctx, cmd_name)

        # If command not found and we have telemetry set up
        if cmd is None and self.telemetry and self.logger:
            self.logger.info(f"Command not found: {cmd_name}")

            try:
                # Create a friendly error message with suggestions
                suggestions = self._get_command_suggestions(cmd_name)
                suggestion_msg = ""
                if suggestions:
                    suggestion_msg = f" Did you mean {', '.join(suggestions)}?"

                # Record the error
                self.telemetry.record_error(
                    Exception(f"No such command '{cmd_name}'.{suggestion_msg}"),
                    command="cli",
                    origin=ErrorOrigin.USER_INPUT,
                    error_type=ErrorType.INVALID_COMMAND,
                    metadata={
                        "attempted_command": cmd_name,
                        "error_category": "command_not_found",
                        "suggestions": (
                            ", ".join(suggestions) if suggestions else "none"
                        ),
                    },
                )

            except Exception as e:
                # Don't let error tracking affect command processing
                if self.logger:
                    self.logger.debug(f"Error tracking invalid command: {e}")

        return cmd

    def _get_command_suggestions(self, cmd_name: str) -> List[str]:
        """Get command suggestions based on similarity."""
        if not cmd_name:
            return []

        # Simple algorithm: commands that start with the same letter
        # or have >50% of letters in common
        suggestions = []
        for valid_cmd in self.valid_commands:
            # Commands with the same first letter
            if valid_cmd.startswith(cmd_name[0]):
                suggestions.append(valid_cmd)
                continue

            # Check for overall similarity
            common_chars = set(valid_cmd) & set(cmd_name)
            if len(common_chars) > len(cmd_name) / 2:
                suggestions.append(valid_cmd)

        return suggestions[:3]  # Limit to top 3 suggestions


class CliCommandTracker:
    """
    Tracks CLI command usage and errors, particularly invalid commands.

    This class creates and configures a telemetry-enabled Click command group
    that can track when users attempt to use commands that don't exist,
    providing visibility into CLI usage errors that would otherwise be missed.

    Usage:
      In CommandRegistry.create_cli():
        tracker = self.injector.get(CliCommandTracker)
        cli = tracker.create_cli_group("idrcli", "My CLI tool description")
        # (Add commands to cli)
        return cli
    """

    @inject
    def __init__(self, telemetry: Telemetry, logger: CliLogger):
        """Initialize with required services."""
        self.telemetry = telemetry
        self.logger = logger

    def create_cli_group(self, name: str, help_text: str) -> click.Group:
        """
        Create a telemetry-enabled Click command group.

        Args:
            name: The command name
            help_text: Help text for the command

        Returns:
            A Click Group with telemetry tracking enabled
        """
        # Create the custom group with explicit typing
        cli_group = cast(click.Group, TelemetryEnabledGroup(name=name, help=help_text))

        # Configure it with our services
        if isinstance(cli_group, TelemetryEnabledGroup):
            cli_group.set_services(self.telemetry, self.logger)

        return cli_group
