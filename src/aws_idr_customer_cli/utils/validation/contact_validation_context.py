from contextlib import contextmanager
from typing import Any, Generator

from aws_idr_customer_cli.core.interactive.ui import InteractiveUI
from aws_idr_customer_cli.utils.validation.base_validation_context import (
    BaseValidationContext,
)
from aws_idr_customer_cli.utils.validation.validator import (
    ValidationError,
    validate_contact_email,
    validate_contact_name,
    validate_contact_phone,
)


class ContactValidationContext(BaseValidationContext):
    """Validation context with UI for contact validation."""

    def contact_name(self, prompt: str = "Contact name", default: str = "") -> Any:
        """Prompt for contact name with validation and retry."""
        return self.get_with_retry(prompt, validate_contact_name, default)

    def contact_email(self, prompt: str = "Contact email", default: str = "") -> Any:
        """Prompt for contact email with validation and retry."""
        return self.get_with_retry(prompt, validate_contact_email, default)

    def contact_phone(self, prompt: str = "Contact phone", default: str = "") -> Any:
        """Prompt for contact phone with validation and retry."""
        return self.get_with_retry(prompt, validate_contact_phone, default)


@contextmanager
def validated_contact_input(
    ui: InteractiveUI,
) -> Generator[ContactValidationContext, None, None]:
    """Context manager for validation with UI - no DI needed."""
    try:
        yield ContactValidationContext(ui)
    except ValidationError as e:
        ui.display_error(f"❌ Validation failed: {e.message}")
        raise
