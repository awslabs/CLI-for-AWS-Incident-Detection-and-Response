from abc import ABC, abstractmethod
from typing import Any


class CommandBase(ABC):
    """Base class for all CLI commands."""

    @abstractmethod
    def execute(self, **kwargs: Any) -> Any:
        """Execute command with keyword arguments."""
        pass

    def output(self, result: Any) -> Any:
        """Handle command output. Can be overridden by commands."""
        pass
