import functools
from typing import Any, Callable, Dict, Optional, TypeVar

import click

from aws_idr_customer_cli.utils.telemetry_service import Telemetry

# Define type variables for better type hints
F = TypeVar("F", bound=Callable[..., Any])


def get_telemetry_from_context() -> Telemetry:
    """Get telemetry from Click context or create minimal instance."""
    ctx = click.get_current_context(silent=True)
    if not ctx:
        # Return a mock telemetry instance for testing
        from unittest.mock import MagicMock

        mock_telemetry = MagicMock()
        # Create a track method that returns a decorator that just calls the function
        mock_telemetry.track = lambda **kwargs: lambda func: func
        return mock_telemetry
    from typing import cast

    return cast(Telemetry, ctx.obj["injector"].get(Telemetry))


# Define a track function that handles both decorator forms
def track(
    func: Optional[Callable[..., Any]] = None,
    namespace: Optional[str] = None,
    operation: Optional[str] = None,
    dimensions: Optional[Dict[str, str]] = None,
) -> Any:
    """Track function execution with telemetry."""

    # The actual decorator that will be returned
    def actual_decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Get telemetry instance
            telemetry = get_telemetry_from_context()

            # Get track decorator from telemetry service with explicit params
            track_decorator = telemetry.track(
                namespace=namespace, operation=operation, dimensions=dimensions
            )

            # Apply the decorator to the function and call it
            return track_decorator(fn)(*args, **kwargs)

        return wrapper

    # Handle both @track and @track() patterns
    if func is not None:
        return actual_decorator(func)
    return actual_decorator
