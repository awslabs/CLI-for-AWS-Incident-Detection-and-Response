from typing import Any, Callable

from aws_idr_customer_cli.core.interactive.ui import InteractiveUI
from aws_idr_customer_cli.utils.validation.validator import ValidationError


class BaseValidationContext:
    """Base validation context with UI and common retry logic."""

    def __init__(self, ui: InteractiveUI):
        self.ui = ui

    def get_with_retry(
        self,
        prompt: str,
        validator: Callable[[Any], Any],
        default: str = "",
        max_retries: int = 3,
    ) -> Any:
        """Get input with validation and automatic retry on error."""
        for attempt in range(max_retries):
            try:
                value = self.ui.prompt_input(prompt, default if default else None)
                return validator(value)
            except ValidationError as e:
                self.ui.display_error(f"❌ {e.message}")
                if attempt == max_retries - 1:  # Last attempt
                    self.ui.display_error(
                        "Maximum attempts reached. Please re-initiate the command"
                    )
                    raise e

        raise ValidationError("Maximum validation attempts exceeded")
