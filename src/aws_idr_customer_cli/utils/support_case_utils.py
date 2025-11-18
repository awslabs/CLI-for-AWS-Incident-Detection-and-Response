import re
from typing import Callable, Optional

from aws_idr_customer_cli.core.interactive.ui import InteractiveUI
from aws_idr_customer_cli.exceptions import SupportCaseAlreadyExistsError
from aws_idr_customer_cli.services.support_case_service import SupportCaseService


def extract_case_id_from_error(error_message: str) -> Optional[str]:
    """Extract support case ID from SupportCaseAlreadyExistsError message."""
    match = re.search(r"case ID:\s*([^\s\n.]+)", error_message)
    if match:
        return match.group(1)
    return None


def handle_duplicate_support_case_interactive(
    ui: InteractiveUI,
    support_case_service: SupportCaseService,
    session_id: str,
    error: SupportCaseAlreadyExistsError,
    workload_name: str,
    update_prompt: str = "Would you like to update it with your new information?",
    display_case_callback: Optional[Callable[[str], None]] = None,
) -> Optional[str]:
    """Handle interactive prompt when a duplicate support case is detected."""
    existing_case_id = extract_case_id_from_error(str(error))

    if not existing_case_id:
        ui.display_warning(str(error))
        return None

    ui.display_warning(f"Support case already exists for '{workload_name}'")
    ui.display_info(f"   Case ID: {existing_case_id}")

    update_case = ui.prompt_confirm(update_prompt, default=True)

    if not update_case:
        ui.display_info("⏭️  Skipping support case update")
        return None

    try:
        support_case_service.update_case_with_attachment_set(
            session_id=session_id, case_id=existing_case_id
        )
        ui.display_info("✅ Support case updated successfully")

        if display_case_callback:
            display_case_callback(existing_case_id)

        return existing_case_id

    except Exception as update_error:
        ui.display_error(f"Failed to update case: {update_error}")
        return None
