from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast

from aws_idr_customer_cli.exceptions import (
    SupportCaseAlreadyExistsError,
    SupportCaseNotFoundError,
)
from aws_idr_customer_cli.input.input_resource_discovery import (
    InputResourceDiscovery,
)
from aws_idr_customer_cli.services.file_cache.data import (
    WorkloadOnboard,
)
from aws_idr_customer_cli.services.support_case_service import SupportCaseService
from aws_idr_customer_cli.utils.constants import CommandType, DiscoverMethod
from aws_idr_customer_cli.utils.resource_discovery_utils import (
    discover_resources_by_tags,
    display_selected_resources,
    select_resources,
)
from aws_idr_customer_cli.utils.session.interactive_session import (
    ACTION_BACK,
    ACTION_KEY,
    ACTION_PAUSE,
    ACTION_RETRY,
    MSG_RESUMING_SESSION,
    STEP_NAME,
    STYLE_BLUE,
    STYLE_DIM,
    STYLE_GREEN,
    STYLE_YELLOW,
    InteractiveSession,
    session_step,
)
from aws_idr_customer_cli.utils.session.session_store import SessionStore
from aws_idr_customer_cli.utils.support_case_utils import (
    handle_duplicate_support_case_interactive,
)
from aws_idr_customer_cli.utils.validation.validator import (
    Validate,
)
from aws_idr_customer_cli.utils.workload_meta_data_collection_utils import (
    collect_workload_info,
    display_workload_info_summary,
    ensure_workload_onboard,
    review_and_update_workload,
)

# workload constants
WORKLOAD_KEY = "workload"
RESOURCES_KEY = "resources"
SELECTED_RESOURCES_KEY = "selected_resources"
# support case constants
SUPPORT_CASE_ID = "case_id"


class WorkloadSession(InteractiveSession):
    """Workload session"""

    # No need for MAX_RETRIES as it's moved to the utility file

    def __init__(
        self,
        store: SessionStore,
        validator: Validate,
        input_resource_discovery: InputResourceDiscovery,
        support_case_service: SupportCaseService,
        account_id: str = "123456789012",  # placeholder
        resume_session_id: Optional[str] = None,
    ) -> None:
        self._input_resource_discovery = input_resource_discovery
        self._validator = validator
        self._support_case_service = support_case_service

        # Initialize discovery method state
        self._discovery_method: Optional[DiscoverMethod] = None
        self._total_resources_discovered = 0
        super().__init__(
            CommandType.WORKLOAD_REGISTRATION, account_id, store, resume_session_id
        )

    def _ensure_discovery_methods_list(self) -> List[DiscoverMethod]:
        """Ensure discovery methods list exists and return it."""
        if not self.submission:
            raise RuntimeError("No submission available")

        if not self.submission.resource_discovery_methods:
            self.submission.resource_discovery_methods = []

        return cast(List, self.submission.resource_discovery_methods)

    def _add_discovery_method(self, method: DiscoverMethod) -> None:
        """Add discovery method to submission, avoiding duplicates."""
        methods = self._ensure_discovery_methods_list()

        if method not in methods:
            methods.append(method)

        self._discovery_method = method

    def _display_workload_info_summary(self) -> None:
        """Display workload information summary."""
        display_workload_info_summary(self.ui, self.submission)

    def _ensure_workload_onboard(self) -> WorkloadOnboard:
        """Ensure workload_onboard exists and return it."""
        return ensure_workload_onboard(self.submission)

    @session_step("Collect Workload Information", order=1)
    def _collect_workload_info(self) -> Dict[str, Any]:
        """Collect basic workload information."""
        return cast(
            Dict[str, Any],
            collect_workload_info(self.ui, self.submission, self._save_progress),
        )

    @session_step("Review and Update Workload Information", order=2)
    def _review_and_update_workload(self) -> Dict[str, Any]:
        """Review and update workload information with correction workflow."""
        return cast(
            Dict[str, Any],
            review_and_update_workload(self.ui, self.submission, self._save_progress),
        )

    @session_step("Select Discovery Method", order=3)
    def select_discovery_method(self) -> Dict[str, str]:
        """Select resource discovery method."""
        self.ui.display_header("Resource Discovery Method")

        methods = [
            "Tag-based discovery",
            "← Back to workload info",
        ]

        choice = self.ui.select_option(
            methods, "How would you like to discover resources?"
        )

        # Back
        if choice == 1:
            return {ACTION_KEY: ACTION_BACK}

        method_map = {0: DiscoverMethod.TAG}
        selected_method = method_map[choice]

        # Store in submission and update instance variable
        self._add_discovery_method(method=selected_method)

        self._save_progress()

        self.ui.display_info(f"✅ Selected: {methods[choice]}")
        return {}

    @session_step("Discover Eligible Resources", order=4)
    def discover_resources(self) -> Dict[str, str]:
        """Execute resource discovery using input handler."""
        if not self._discovery_method:
            self.ui.display_error("No discovery method selected")
            return {ACTION_KEY: ACTION_BACK}

        self.ui.display_header("Resource Discovery")

        if self._discovery_method == DiscoverMethod.TAG:
            regions = (
                self.submission.workload_onboard.regions
                if self.submission.workload_onboard
                else ["us-east-1"]
            )

            result = discover_resources_by_tags(self._input_resource_discovery, regions)

            # Handle navigation action
            if isinstance(result, dict) and result.get("action") == "back":
                return result

            # Extract resources and tags from tuple result
            resources, tag_filters = result
            self._total_resources_discovered = len(resources)

            # Store resources and tags in submission
            if not self.submission:
                raise RuntimeError("No submission available")
            self.submission.resource_arns_selected = resources
            self.submission.resource_tags = tag_filters
        else:
            if not self.submission:
                raise RuntimeError("No submission available")
            self.submission.resource_arns_selected = []

        resource_count = (
            len(self.submission.resource_arns_selected)
            if self.submission.resource_arns_selected
            else 0
        )
        self.ui.display_info(
            message=f"✅ Discovered {resource_count} eligible resources for all given regions",
            style=STYLE_BLUE,
        )
        self.ui.display_info(
            message="ℹ️  Resources not eligible for monitoring like IAM roles, security "
            "groups, and subnets are excluded",
            style="dim",
        )
        return {}

    @session_step("Select Resources", order=5)
    def select_resources(self) -> Dict[str, str]:
        """Production-grade resource selection using MLOAdapter."""
        if not self.submission or not self.submission.resource_arns_selected:
            self.ui.display_warning(
                "No resources were discovered. Skipping resource selection."
            )
            return {}

        result = select_resources(
            ui=self.ui, resource_arns=self.submission.resource_arns_selected
        )

        # Handle navigation action
        if isinstance(result, dict) and result.get(ACTION_KEY) in [
            ACTION_RETRY,
            ACTION_BACK,
        ]:
            return result

        # Update submission directly
        self.submission.resource_arns_selected = result
        return {}

    @session_step("Create Support Case", order=6)
    def create_support_case(self) -> Dict[str, Any]:
        """Create AWS Support Case for workload onboard."""
        try:
            display_selected_resources(self.ui, self.submission.resource_arns_selected)

            continue_to_support_case = self.ui.prompt_confirm(
                (
                    "Are you ready to submit the workload with the above information "
                    "and create a support case?"
                ),
                default=True,
            )
            if not continue_to_support_case:
                self.ui.display_warning(
                    "❌ Workload registration and Support case creation cancelled by user"
                )
                return {ACTION_KEY: ACTION_PAUSE}

            workload = self._ensure_workload_onboard()
            workload.contacts_approval_timestamp = datetime.now(timezone.utc)
            self._save_progress()

            case_id = self._support_case_service.create_case(self.session_id)
            workload.support_case_id = case_id

            self.ui.display_info("✅ A support case has been created")
            self._display_support_case(case_id)
            return {}

        except SupportCaseAlreadyExistsError as e:

            case_id = handle_duplicate_support_case_interactive(
                ui=self.ui,
                support_case_service=self._support_case_service,
                session_id=self.session_id,
                error=e,
                workload_name=self.submission.workload_onboard.name,
                update_prompt="Would you like to update it with your new workload information?",
                display_case_callback=self._display_support_case,
            )

            if case_id:
                workload = self._ensure_workload_onboard()
                workload.support_case_id = case_id

            return {}

    @session_step("Alarm creation handoff", order=7)
    def _handoff_to_alarm_creation(self) -> Dict[str, Any]:
        """Handle workload registration completion and workflow transition."""

        self.ui.display_info(
            "🎉 Workload information collection completed!", style=STYLE_GREEN
        )

        # Show summary of what was collected
        self._display_final_workload_summary()

        # Ask about next phase
        continue_to_alarms = self.ui.prompt_confirm(
            "Would you like to continue with alarm creation for this workload?",
            default=True,
        )

        if continue_to_alarms:
            self.ui.display_info(
                "🚀 Transitioning to alarm creation phase...", style=STYLE_BLUE
            )

            # Mark workload phase handoff to alarm creation
            self.submission.workload_to_alarm_handoff = True

            # placeholder for now
            self.ui.display_info(
                f"Continue with: awsidr create-alarms --resume {self.session_id}"
            )

            # Return special status but let session continue normally
            return {"workflow_transition": "alarm_creation"}
        else:
            self.submission.workload_to_alarm_handoff = False
            self.ui.display_info(
                f"💾 Workload saved. Resume later with: "
                f"awsidr create-alarms --resume {self.session_id}",
                style=STYLE_YELLOW,
            )
            return {ACTION_KEY: ACTION_PAUSE}

    def _display_final_workload_summary(self) -> None:
        """Display comprehensive workload summary before completion."""
        if not self.submission or not self.submission.workload_onboard:
            return

        workload = self.submission.workload_onboard
        resource_count = (
            len(self.submission.resource_arns_selected)
            if self.submission.resource_arns_selected
            else 0
        )

        self.ui.display_result(
            "📋 Workload registration summary",
            {
                "Workload name": workload.name,
                "Regions": ", ".join(workload.regions),
                "Total resources discovered": f"{self._total_resources_discovered}",
                "Resources selected for onboarding": f"{resource_count}",
            },
        )

    def _display_resume_info(self) -> None:
        """Display resume information with context from previous steps."""
        if not self.submission:
            return

        self.ui.display_info(
            message=MSG_RESUMING_SESSION.format(self.current_step + 1, len(self.steps)),
            style=STYLE_BLUE,
        )

        self.ui.display_info(
            "ℹ️  If you have recently updated the AWS IDR CLI, resuming an old "
            "session may take you back to Step 1 to allow you to review previously "
            "entered information to ensure accuracy and compatibility with the current version.",
            style=STYLE_DIM,
        )

        # Show step-specific context based on current step
        self._display_step_context()

    def _display_support_case(self, support_case_id: str) -> None:
        """Display support case information."""
        try:
            case = self._support_case_service.describe_case(support_case_id)
            self.ui.display_result(
                "📋 Support Case Information",
                {
                    "Subject": case.get("subject"),
                    "Display ID": case.get("displayId"),
                    "Status": case.get("status"),
                },
            )
        except SupportCaseNotFoundError:
            self.ui.display_warning(f"Support case {support_case_id} not found")

    def _display_step_context(self) -> None:
        """Display context information from completed steps."""
        if not self.submission:
            return

        step_names = [getattr(step, STEP_NAME) for step in self.steps]
        current_step_name = (
            step_names[self.current_step]
            if self.current_step < len(step_names)
            else "Unknown"
        )

        self.ui.display_header(
            f"Resuming: {current_step_name}",
            "Here's what was completed in previous steps:",
        )

        # Step 1-2: Workload Information (show if step >= 2)
        if self.current_step >= 2 and self.submission.workload_onboard:
            self._display_workload_context()

        # Step 3: Discovery Method (show if step >= 3)
        if self.current_step >= 3:
            self._display_discovery_method_context()

        # Step 4: Resource Discovery (show if step >= 4)
        if self.current_step >= 4 and self.submission.resource_arns_selected:
            self._display_resource_discovery_context()

        # Step 5: Resource Selection (show if step >= 5)
        if self.current_step >= 5:
            self._display_resource_selection_context()

    def _display_workload_context(self) -> None:
        """Display workload information context."""
        if not self.submission.workload_onboard:
            return

        workload = self.submission.workload_onboard
        self.ui.display_result(
            "📋 Workload Information",
            {
                "Name": workload.name,
                "Regions": ", ".join(workload.regions),
            },
        )

    def _display_discovery_method_context(self) -> None:
        """Display discovery method context."""
        method_name = (
            ",".join(self.submission.resource_discovery_methods)
            if self.submission.resource_discovery_methods
            else "Unknown method"
        )
        self.ui.display_info(f"🔍 Discovery Method: {method_name}", style=STYLE_BLUE)

    def _display_resource_discovery_context(self) -> None:
        """Display resource discovery context with summary."""
        if not self.submission.resource_arns_selected:
            return

        # Group resources by service for summary
        resource_summary = {}
        for resource in self.submission.resource_arns_selected:
            service = resource.type
            if service not in resource_summary:
                resource_summary[service] = 0
            resource_summary[service] += 1

        self.ui.display_info(
            f"📦 Resources Discovered: {len(self.submission.resource_arns_selected)} total",
            style=STYLE_BLUE,
        )

        # Show breakdown by service
        for service, count in resource_summary.items():
            self.ui.display_info(f"  • {service}: {count} resource(s)", style=STYLE_DIM)

    def _display_resource_selection_context(self) -> None:
        """Display resource selection context."""
        if not self.submission.resource_arns_selected:
            self.ui.display_info(
                "⚠️  No resources were selected in previous steps", style="yellow"
            )
            return

        selected_count = len(self.submission.resource_arns_selected)
        self.ui.display_info(
            f"✅ Resource Selection: {selected_count} resource(s) selected",
            style=STYLE_BLUE,
        )

    def _display_tag_discovery_context(self) -> None:
        """Display tag information used for discovery."""
        if (
            hasattr(self.submission, "discovery_tags")
            and self.submission.discovery_tags
        ):
            tag_info = []
            for key, values in self.submission.discovery_tags.items():
                if isinstance(values, list):
                    tag_info.append(f"{key}={','.join(values)}")
                else:
                    tag_info.append(f"{key}={values}")

            self.ui.display_info(
                f"🏷️  Tags Used: {'; '.join(tag_info)}", style=STYLE_DIM
            )
