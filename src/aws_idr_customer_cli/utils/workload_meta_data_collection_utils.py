"""Utility functions for workload metadata collection."""

from typing import Any, Callable, Dict, List

from retry import retry

from aws_idr_customer_cli.core.interactive.ui import InteractiveUI
from aws_idr_customer_cli.exceptions import (
    MissingInputFieldError,
    ValidationError,
)
from aws_idr_customer_cli.services.file_cache.data import (
    OnboardingSubmission,
    WorkloadOnboard,
)
from aws_idr_customer_cli.utils.session.interactive_session import (
    ACTION_BACK,
    ACTION_KEY,
)

# workload constants
WORKLOAD_NAME = "name"
WORKLOAD_REGIONS = "regions"

# Maximum retries for validation
MAX_RETRIES = 3


def display_workload_info_summary(
    ui: InteractiveUI, submission: OnboardingSubmission
) -> None:
    """Display workload information summary."""
    if not submission or not submission.workload_onboard:
        ui.display_warning("No workload information available")
        return

    workload = submission.workload_onboard
    summary = {"Name": workload.name}

    # Only show regions if they were collected
    if workload.regions:
        summary["Regions"] = ", ".join(workload.regions)

    ui.display_result("Workload Information Summary", summary)


def ensure_workload_onboard(submission: OnboardingSubmission) -> WorkloadOnboard:
    """Ensure workload_onboard exists and return it."""
    if not submission:
        raise RuntimeError("No submission available")

    if not submission.workload_onboard:
        submission.workload_onboard = WorkloadOnboard(
            support_case_id=None,
            name="",
            regions=[],  # Empty by default, will be populated when needed
        )

    return submission.workload_onboard


def prompt_for_field(
    ui: InteractiveUI,
    prompt: str,
    validator: Callable[[Any], Any],
    default: str = "",
) -> Any:
    """Prompt for field with validation."""
    value = prompt_with_validation(ui, prompt, validator, default)
    return value


@retry(exceptions=ValidationError, tries=MAX_RETRIES)
def prompt_with_validation(
    ui: InteractiveUI,
    prompt: str,
    validator: Callable[[Any], Any],
    default: str = "",
) -> Any:
    """Prompt with validation and retry on error. Returns None if interrupted."""
    try:
        value = ui.prompt_input(prompt, default)
        return validator(value)
    except ValidationError as e:
        ui.display_error(str(e))
        raise


def prompt_for_workload_info(
    ui: InteractiveUI,
    submission: OnboardingSubmission,
    save_progress_callback: Callable,
    skip_regions: bool = False,
) -> None:
    """Prompt for workload information directly updating submission."""
    from aws_idr_customer_cli.utils.validation.workload_validation import (
        validate_workload_name,
        validate_workload_regions,
    )

    workload = ensure_workload_onboard(submission)

    helper_text = (
        "💡 Enter a descriptive name for this workload "
        "(e.g. PaymentsService-Prod, DataPipeline-Dev) "
        "to represent a group of resources that deliver "
        "your application or service. AWS uses this name to "
        "identify your workload during an incident. "
    )
    ui.display_info(helper_text, style="dim")

    name = prompt_for_field(
        ui,
        "Workload name",
        validate_workload_name,
        workload.name,
    )
    if name is None:
        raise MissingInputFieldError("Workload name is required")
    workload.name = name

    if not skip_regions:
        regions_str = ",".join(workload.regions)
        regions = prompt_for_field(
            ui,
            "Regions (comma-separated)",
            validate_workload_regions,
            regions_str,
        )
        if regions is None:
            raise MissingInputFieldError("Regions are required")
        workload.regions = regions

    save_progress_callback()


def format_field_value(submission: OnboardingSubmission, field_key: str) -> str:
    """Format field value for display."""
    if not submission or not submission.workload_onboard:
        return "(empty)"

    workload = submission.workload_onboard
    value = getattr(workload, field_key, "")

    if field_key == "regions" and isinstance(value, list):
        return ", ".join(value)
    return str(value) if value else "(empty)"


def offer_correction_workflow(
    ui: InteractiveUI,
    submission: OnboardingSubmission,
    save_progress_callback: Callable,
) -> bool:
    """Offer user option to modify previous entries."""
    from aws_idr_customer_cli.utils.validation.workload_validation import (
        validate_workload_name,
        validate_workload_regions,
    )

    if not submission or not submission.workload_onboard:
        return False

    if not ui.prompt_confirm("Would you like to modify any information?", False):
        return False

    workload = submission.workload_onboard
    fields = [
        (WORKLOAD_NAME, "Workload name", validate_workload_name, workload.name),
        (
            WORKLOAD_REGIONS,
            "Regions",
            validate_workload_regions,
            ",".join(workload.regions),
        ),
    ]

    options = [
        f"{field[1]}: {format_field_value(submission, field[0])}" for field in fields
    ]

    choice = ui.select_option(options, "Select field to modify")

    if choice >= len(fields):
        return False

    field_key, field_name, validator, current_value = fields[choice]
    display_value = (
        current_value
        if field_key != "regions"
        else (
            ",".join(current_value)
            if isinstance(current_value, list)
            else current_value
        )
    )

    new_value = prompt_for_field(ui, field_name, validator, str(display_value))
    if new_value is not None:
        setattr(workload, field_key, new_value)
        ui.display_info(f"✅ {field_name} updated")
        save_progress_callback()

    return True


def collect_regions(ui: InteractiveUI, single_region: bool = False) -> List[str]:
    """Collect region(s) from user input."""
    from aws_idr_customer_cli.utils.validation.workload_validation import (
        validate_workload_regions,
    )

    prompt_text = "Region" if single_region else "Regions (comma-separated)"
    regions = prompt_for_field(
        ui,
        prompt_text,
        validate_workload_regions,
        "",
    )

    if not regions:
        return []

    # If single_region is True, only return the first region
    return [regions[0]] if single_region else regions


def are_all_fields_collected(
    ui: InteractiveUI,
    submission: OnboardingSubmission,
    save_progress_callback: Callable,
    skip_regions: bool = False,
) -> bool:
    """Collect all workload fields. Returns False if interrupted."""
    try:
        prompt_for_workload_info(ui, submission, save_progress_callback, skip_regions)
        return True
    except MissingInputFieldError:
        return False
    except ValidationError:
        return False


def collect_workload_info(
    ui: InteractiveUI,
    submission: OnboardingSubmission,
    save_progress_callback: Callable,
    skip_regions: bool = False,
) -> Dict[str, Any]:
    """Collect basic workload information."""
    ui.display_info("💡 You can review and update this information in the next step")
    if not are_all_fields_collected(
        ui, submission, save_progress_callback, skip_regions
    ):
        return {ACTION_KEY: ACTION_BACK}

    ui.display_info("✅ Workload information collected")
    display_workload_info_summary(ui, submission)
    return {}


def review_and_update_workload(
    ui: InteractiveUI,
    submission: OnboardingSubmission,
    save_progress_callback: Callable,
) -> Dict[str, Any]:
    """Review and update workload information with correction workflow."""
    try:
        # Offer correction workflow until satisfied
        while offer_correction_workflow(ui, submission, save_progress_callback):
            display_workload_info_summary(ui, submission)

        ui.display_info("✅ Workload information finalized")
        return {}
    except KeyboardInterrupt:
        raise
