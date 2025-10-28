"""Utility for tracking CLI execution mode."""

from enum import Enum
from typing import Optional


class ExecutionMode(str, Enum):
    """CLI execution modes."""

    INTERACTIVE = "interactive"
    NON_INTERACTIVE = "non-interactive"


_execution_mode: Optional[ExecutionMode] = None


def set_execution_mode(mode: ExecutionMode) -> None:
    """Set the current execution mode."""
    global _execution_mode
    _execution_mode = mode


def get_execution_mode() -> Optional[ExecutionMode]:
    """Get the current execution mode."""
    return _execution_mode
