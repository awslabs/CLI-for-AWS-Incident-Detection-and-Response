import json
from typing import Any, Dict

from injector import inject

from aws_idr_customer_cli.core.interactive.ui import InteractiveUI
from aws_idr_customer_cli.input.input_resource_discovery import InputResourceDiscovery
from aws_idr_customer_cli.models.non_interactive_config import (
    OutputFormat,
    WorkloadRegistrationConfig,
)
from aws_idr_customer_cli.services.file_cache.data import (
    OnboardingStatus,
    OnboardingSubmission,
    ProgressTracker,
)
from aws_idr_customer_cli.services.file_cache.file_cache_service import FileCacheService
from aws_idr_customer_cli.services.non_interactive_base_service import (
    NonInteractiveServiceBase,
)
from aws_idr_customer_cli.services.support_case_service import SupportCaseService
from aws_idr_customer_cli.utils.execution_mode import (
    ExecutionMode,
)
from aws_idr_customer_cli.utils.resource_discovery_utils import (
    display_selected_resources,
)
from aws_idr_customer_cli.utils.session.session_store import SessionStore
from aws_idr_customer_cli.utils.validation.validator import Validate

# Constants
PROGRESS_STEPS = ["workload_info", "discovery", "selection", "submission"]


class NonInteractiveWorkloadService(NonInteractiveServiceBase):
    """Service for non-interactive workload registration that performs all interactive steps."""

    @inject
    def __init__(
        self,
        ui: InteractiveUI,
        store: SessionStore,
        input_resource_discovery: InputResourceDiscovery,
        validator: Validate,
        support_case_service: SupportCaseService,
        file_cache_service: FileCacheService,
    ) -> None:
        super().__init__(
            ui=ui,
            store=store,
            input_resource_discovery=input_resource_discovery,
            validator=validator,
            support_case_service=support_case_service,
            file_cache_service=file_cache_service,
        )

    def _display_dry_run_specific_info(self) -> None:
        """Display dry run info specific to workload registration."""
        self.ui.display_info("Support case creation will be skipped", style="yellow")

    def register_workload_from_config(
        self, config: Dict[str, Any], account_id: str
    ) -> None:
        """Execute complete workload registration from config data."""
        config_obj = WorkloadRegistrationConfig.from_dict(config)
        json_output = dict()
        try:
            submission = self.execute_from_config(config_obj, account_id)
            if config_obj.options.output_format == OutputFormat.JSON:
                json_output["status"] = "success"
                json_output["data"] = self._create_filtered_json_output(submission)
                print(json.dumps(json_output, indent=2))
        except Exception as e:
            if config_obj.options.output_format == OutputFormat.JSON:
                json_output["status"] = "failed"
                json_output["error"] = str(e)
                print(json.dumps(json_output, indent=2))
            else:
                raise e

    def execute_from_config(
        self, config_obj: WorkloadRegistrationConfig, account_id: str
    ) -> OnboardingSubmission:
        """Execute workload registration from config data."""
        self.set_output_format(config_obj.options.output_format)

        dry_run_mode = config_obj.options.dry_run
        if dry_run_mode:
            self._display_dry_run_header()

        self.validate_config(
            workload_name=config_obj.workload.name,
            workload_regions=config_obj.workload.regions,
            discovery_config=config_obj.discovery,
        )

        workload = self._create_workload_data(
            name=config_obj.workload.name,
            regions=config_obj.workload.regions,
        )

        discovered_resources = []
        self.ui.display_info(
            f"Starting resource discovery using method: {config_obj.discovery.method.value}"
        )
        discovered_resources = self._discover_resources(
            discovery_config=config_obj.discovery,
            regions=config_obj.workload.regions,
        )
        self.ui.display_info(
            f"✅ Discovered {len(discovered_resources)} resources", style="green"
        )

        workload_tracker = ProgressTracker(
            current_step=len(PROGRESS_STEPS),
            total_steps=len(PROGRESS_STEPS),
            step_name=OnboardingStatus.COMPLETED.value,
            completed_steps=PROGRESS_STEPS,
        )

        submission = self._create_submission(
            workload=workload,
            resources=discovered_resources,
            account_id=account_id,
            progress_tracker=workload_tracker,
            status=OnboardingStatus.COMPLETED,
        )

        submission.execution_mode = ExecutionMode.NON_INTERACTIVE

        session_id = self.store.create(submission)

        display_selected_resources(self.ui, discovered_resources)

        case_id = self._handle_support_case_creation(
            session_id=session_id,
            dry_run_mode=dry_run_mode,
        )

        workload.support_case_id = case_id
        self.store.update(session_id, submission)

        self.ui.display_info("✅ Registration completed successfully", style="green")
        summary_title = "📋 Workload registration summary"

        summary_data = {
            "Workload name": workload.name,
            "Regions": ", ".join(workload.regions),
            "Resources selected for onboarding": f"{len(discovered_resources)}",
        }

        if dry_run_mode:
            summary_data["Mode"] = "DRY RUN - No actual changes made"

        self.ui.display_result(summary_title, summary_data)

        return submission
