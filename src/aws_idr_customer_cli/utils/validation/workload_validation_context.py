from contextlib import contextmanager
from typing import Generator, List

from aws_idr_customer_cli.core.interactive.ui import InteractiveUI
from aws_idr_customer_cli.utils.validation.base_validation_context import (
    BaseValidationContext,
)
from aws_idr_customer_cli.utils.validation.validator import ValidationError
from aws_idr_customer_cli.utils.validation.workload_validation import (
    validate_workload_name,
    validate_workload_regions,
)


class WorkloadValidationContext(BaseValidationContext):
    """Workload validation context with UI."""

    def workload_name(self, prompt: str = "Workload name", default: str = "") -> str:
        """Prompt for workload name with validation and retry."""
        result = self.get_with_retry(prompt, validate_workload_name, default)
        return str(result)

    def workload_regions(
        self, prompt: str = "AWS regions (comma-separated)", default: str = ""
    ) -> List[str]:
        """Prompt for workload regions with validation and retry."""
        result = self.get_with_retry(prompt, validate_workload_regions, default)
        return list(result)  # type: ignore


@contextmanager
def validated_workload_input(
    ui: InteractiveUI,
) -> Generator[WorkloadValidationContext, None, None]:
    """Context manager for workload validation with UI - no DI needed."""
    try:
        yield WorkloadValidationContext(ui)
    except ValidationError as e:
        ui.display_error(f"❌ Workload validation failed: {e.message}")
        raise
