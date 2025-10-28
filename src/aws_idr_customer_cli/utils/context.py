"""Context variables for runtime configuration."""

from contextvars import ContextVar

integration_test_mode: ContextVar[bool] = ContextVar(
    "integration_test_mode", default=False
)


def set_integration_test_mode(enabled: bool) -> None:
    """Set the integration test mode for the current context.

    Args:
        enabled: True to enable integration test mode, False to disable
    """
    integration_test_mode.set(enabled)


def is_integration_test_mode() -> bool:
    """Check if integration test mode is enabled in the current context.

    Returns:
        True if integration test mode is enabled, False otherwise
    """
    return integration_test_mode.get()
