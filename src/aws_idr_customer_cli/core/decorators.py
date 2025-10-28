import time
from functools import wraps
from typing import Any, Callable, Dict, Optional, Type, TypeVar

import click

from aws_idr_customer_cli.core.command_base import CommandBase
from aws_idr_customer_cli.modules.logging import LoggingModule

CommandClass = TypeVar("CommandClass", bound=Type[CommandBase])


def command(
    name: str, help: Optional[str] = None
) -> Callable[[CommandClass], CommandClass]:
    """Command decorator with proper type hints."""

    def decorator(cls: CommandClass) -> CommandClass:
        original_execute = getattr(cls, "execute")

        @click.command(name=name, help=help or cls.__doc__)
        @click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
        @click.option("--debug", is_flag=True, help="Enable debug mode")
        @click.pass_context
        @wraps(original_execute)
        def wrapped_execute(
            ctx: click.Context,
            verbose: bool = False,
            debug: bool = False,
            **kwargs: Dict[str, Any],
        ) -> Any:
            if not ctx.obj or "injector" not in ctx.obj:
                raise click.ClickException("Dependency injector not found")
            injector = ctx.obj["injector"]

            # Configure logging if command-level options are provided (override global)
            LoggingModule.configure_console_logging(
                injector=injector, verbose=verbose, debug=debug
            )

            instance = injector.get(cls)
            # Execute and get result
            result = original_execute(instance, **kwargs)

            # Call the output method with the result
            instance.output(result)

            return result

        cls.execute = wrapped_execute  # type: ignore
        return cls

    return decorator


def option(
    *args: Any, **kwargs: Any
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator for command options."""
    return click.option(*args, **kwargs)


def argument(
    *args: Any, **kwargs: Any
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator for command arguments."""
    return click.argument(*args, **kwargs)


def retry_on_throttle(max_retries: int = 3, initial_backoff: float = 1.0) -> Callable:
    """Retry decorator for handling throttling errors."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if "Throttling" in str(e) or "Rate exceeded" in str(e):
                        if attempt < max_retries - 1:
                            time.sleep(initial_backoff * (2**attempt))
                            continue
                    raise
            return func(*args, **kwargs)

        return wrapper

    return decorator
