from typing import Any, Dict

from aws_idr_customer_cli.core.interactive.ui import InteractiveUI

SLR_ROLE_NAME = "AWSServiceRoleForHealth_EventProcessor"
SLR_SERVICE_NAME = "event-processor.health.amazonaws.com"


def check_and_create_service_linked_role(
    ui: InteractiveUI, iam_manager: Any
) -> Dict[str, Any]:
    """Check if Service Linked Role exists and prompt to create if needed."""
    try:
        ui.display_info(
            "Performing sanity check for Service Linked Role (IDR requirement)..."
        )
        ui.display_info(
            "More details about this requirement can be found at this link: "
        )
        ui.display_info(
            "https://docs.aws.amazon.com/IDR/latest/userguide/idr-gs-access-prov.html"
        )

        if iam_manager.service_linked_role_exists(SLR_ROLE_NAME):
            ui.display_info(
                "✅ Service Linked Role found for IDR alarm ingestion, no action needed"
            )
            return {}

        ui.display_warning("Service Linked Role missing for IDR")
        ui.display_info("IDR requires SLR to ingest alarms from your account")

        create_role = ui.prompt_confirm(
            "Would you like to create the Service Linked Role for IDR now?",
            default=True,
        )

        if create_role:
            role_name = iam_manager.create_service_linked_role(SLR_SERVICE_NAME)
            ui.display_info(f"✅ Created Service Linked Role: {role_name}")
        else:
            ui.display_info("⚠️  Skipped Service Linked Role creation")
            ui.display_info(
                "\n📝 To create the Service Linked Role manually, run:",
                style="blue",
            )
            ui.display_info(
                f"   aws iam create-service-linked-role --aws-service-name {SLR_SERVICE_NAME}",
                style="dim",
            )

    except Exception as e:
        ui.display_error(
            f"Unable to verify/create Service Linked Role status: {str(e)}"
        )
        ui.display_info(
            "You may need to create the Service Linked Role manually if it doesn't exist."
        )
        ui.display_info(
            "\n📝 To create the Service Linked Role manually, run:", style="blue"
        )
        ui.display_info(
            f"   aws iam create-service-linked-role --aws-service-name {SLR_SERVICE_NAME}",
            style="dim",
        )
        return {}

    return {}
