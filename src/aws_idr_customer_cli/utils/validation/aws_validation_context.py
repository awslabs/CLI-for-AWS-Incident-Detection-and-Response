from contextlib import contextmanager
from typing import Any, Dict, Generator, List

from aws_idr_customer_cli.core.interactive.ui import InteractiveUI
from aws_idr_customer_cli.exceptions import ValidationError
from aws_idr_customer_cli.utils.validation.base_validation_context import (
    BaseValidationContext,
)
from aws_idr_customer_cli.utils.validation.validator import Validate


class AWSValidationContext(BaseValidationContext):
    """AWS-specific validation context."""

    def __init__(self, ui: InteractiveUI, validator: Validate):
        super().__init__(ui)
        self.validator = validator

    def tag_key(self, prompt: str = "Tag key", default: str = "") -> Any:
        """Prompt for AWS tag key with validation."""
        return self.get_with_retry(prompt, self._validate_aws_tag_key, default)

    def tag_values(self, prompt: str = "Tag value", default: str = "") -> Any:
        """Prompt for AWS tag value with validation."""

        def parse_multiple_values(input_str: str) -> List[str]:
            if not input_str.strip():
                return []
            values = [v.strip() for v in input_str.split(",")]
            return list(self._validate_aws_tag_values(values))

        result = self.get_with_retry(prompt, parse_multiple_values, default)
        return list(result)

    def tag_filter_pairs(
        self, prompt: str = "Tag filters (key1=val1|val2,key2=val3)", default: str = ""
    ) -> List[Dict[str, Any]]:
        """Prompt for tag filter pairs for searching resources."""
        result = self.get_with_retry(
            prompt, self._validate_aws_tag_filter_pairs, default
        )
        return result  # type: ignore

    def region(self, prompt: str = "Enter a", default: str = "") -> Any:
        """Prompt for AWS region with validation."""
        return self.get_with_retry(prompt, self._validate_aws_region, default)

    def _validate_aws_tag_key(self, value: Any) -> Any:
        """Validate AWS tag key."""
        return self.validator.chain(value, Validate.required, Validate.aws_tag_key)

    def _validate_aws_tag_values(self, value: Any) -> Any:
        """Validate tag values for filtering."""
        return self.validator.aws_tag_values(value)

    def _validate_aws_tag_filter_pairs(self, value: Any) -> Any:
        """Validate tag filter pairs."""
        return self.validator.aws_tag_filter_pairs(value)

    def _validate_aws_region(self, value: Any) -> Any:
        """Validate AWS region."""
        return self.validator.aws_region(value)


@contextmanager
def aws_validation(
    ui: InteractiveUI, validator: Validate
) -> Generator[AWSValidationContext, None, None]:
    """AWS validation context manager."""
    try:
        yield AWSValidationContext(ui, validator)
    except ValidationError as e:
        ui.display_error(f"❌ Validation failed: {e.message}")
        raise
