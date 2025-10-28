from __future__ import annotations

import time
from types import TracebackType
from typing import Any, Dict, Optional, Type

from aws_idr_customer_cli.utils.telemetry_service import Telemetry


class CommandTracker:
    """
    Helper for tracking CLI commands from start to finish.

    Usage:
        tracker = CommandTracker(telemetry, command="alarm", subcommand="create")
        with tracker:
            # Execute command
            result = execute_command()
        # Metrics are automatically recorded
    """

    def __init__(
        self,
        telemetry: Telemetry,
        command: str,
        subcommand: Optional[str] = None,
        region: Optional[str] = None,
        profile: Optional[str] = None,
        flags: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize command tracker.

        Args:
            telemetry: Telemetry service instance
            command: Command name
            subcommand: Subcommand name
            region: AWS region
            profile: AWS profile
            flags: Command flags and options
        """
        self.telemetry = telemetry
        self.command = command
        self.subcommand = subcommand
        self.region = region
        self.profile = profile
        self.flags = flags
        self.start_time = 0.0

    def __enter__(self) -> CommandTracker:
        """Start tracking the command execution."""
        # Record start time
        self.start_time = time.perf_counter()

        self.telemetry.set_command_context(
            self.command, self.subcommand, self.region, self.profile, self.flags
        )
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        duration_ms = (time.perf_counter() - self.start_time) * 1000

        # Record command result
        success = exc_type is None
        self.telemetry.record_command_result(
            success=success, error=exc_val if exc_val else None, duration_ms=duration_ms
        )

        # Record exception
        if exc_val:
            self.telemetry.record_error(
                exc_val,
                command=self.command,
                subcommand=self.subcommand,
                metadata={"command_parameters": self.flags},
            )
