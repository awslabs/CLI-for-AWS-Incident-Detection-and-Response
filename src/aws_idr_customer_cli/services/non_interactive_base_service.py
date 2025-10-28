from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from injector import inject

from aws_idr_customer_cli.core.interactive.ui import InteractiveUI
from aws_idr_customer_cli.input.input_resource_discovery import InputResourceDiscovery
from aws_idr_customer_cli.models.non_interactive_config import (
    AlarmContactsConfig,
    DiscoveryConfig,
    DiscoveryMethod,
    OutputFormat,
)
from aws_idr_customer_cli.services.file_cache.data import (
    AlarmContacts,
    CommandStatusTracker,
    OnboardingStatus,
    OnboardingSubmission,
    ProgressTracker,
    ResourceArn,
    WorkloadOnboard,
)
from aws_idr_customer_cli.services.file_cache.file_cache_service import FileCacheService
from aws_idr_customer_cli.services.support_case_service import SupportCaseService
from aws_idr_customer_cli.utils.arn_utils import (
    build_resource_arn_object,
    extract_resource_id_from_arn,
)
from aws_idr_customer_cli.utils.constants import CLI_VERSION, SCHEMA_VERSION
from aws_idr_customer_cli.utils.execution_mode import get_execution_mode
from aws_idr_customer_cli.utils.hash_utils import calculate_submission_hash
from aws_idr_customer_cli.utils.session.session_store import SessionStore
from aws_idr_customer_cli.utils.validation.validator import (
    Validate,
    validate_contact_email,
    validate_contact_name,
    validate_contact_phone,
)
from aws_idr_customer_cli.utils.validation.workload_validation import (
    validate_workload_name,
    validate_workload_regions,
)
from aws_idr_customer_cli.utils.workload_meta_data_collection_utils import (
    display_workload_info_summary,
)


class NonInteractiveServiceBase(ABC):
    """Base class for non-interactive services providing common functionality."""

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
        self.ui = ui
        self.store = store
        self._input_resource_discovery = input_resource_discovery
        self._validator = validator
        self._support_case_service = support_case_service
        self._file_cache_service = file_cache_service
        self._output_format = OutputFormat.TEXT

    def set_output_format(self, output_format: OutputFormat) -> None:
        """Set the output format for the service."""
        self._output_format = output_format
        # Enable silent mode on UI for JSON output
        if self._output_format == OutputFormat.JSON:
            self.ui.set_silent_mode(True)

    def _should_display_ui(self) -> bool:
        """Check if UI output should be displayed based on output format."""
        return bool(self._output_format == OutputFormat.TEXT)

    def _display_dry_run_header(self) -> None:
        """Display dry run mode header."""
        self.ui.display_header("🔍 DRY RUN MODE ENABLED")
        self.ui.display_info(
            "No mutative changes will be made to your account", style="yellow"
        )
        self._display_dry_run_specific_info()
        self.ui.display_info("")

    @abstractmethod
    def _display_dry_run_specific_info(self) -> None:
        """Display dry run info specific to the service type."""
        pass

    def validate_config(
        self,
        workload_name: str,
        workload_regions: List[str],
        alarm_contacts_config: Optional[AlarmContactsConfig] = None,
        discovery_config: Optional[DiscoveryConfig] = None,
        skip_region_validation: bool = False,
    ) -> None:
        """
        This method validates all inputs before any processing begins.
        """
        # Validate workload information
        validate_workload_name(workload_name)
        if not skip_region_validation:
            validate_workload_regions(",".join(workload_regions))

        # Validate alarm contact information if provided (required fields)
        if alarm_contacts_config:
            # Validate primary contact
            validate_contact_name(alarm_contacts_config.primary.name)
            validate_contact_email(alarm_contacts_config.primary.email)
            validate_contact_phone(alarm_contacts_config.primary.phone or "")

            # Validate escalation contact if provided
            if alarm_contacts_config.escalation:
                validate_contact_name(alarm_contacts_config.escalation.name)
                validate_contact_email(alarm_contacts_config.escalation.email)
                validate_contact_phone(alarm_contacts_config.escalation.phone or "")

        # Validate discovery configuration if provided
        if discovery_config:
            # Validate tags if using tag-based discovery
            if (
                discovery_config.method == DiscoveryMethod.TAGS
                and discovery_config.tags
            ):
                for tag_key, tag_value in discovery_config.tags.items():
                    self._validator.aws_tag_key(tag_key)
                    self._validator.aws_tag_value(tag_value)

            # Validate ARNs if using ARN-based discovery
            elif (
                discovery_config.method == DiscoveryMethod.ARNS
                and discovery_config.arns
            ):
                for arn in discovery_config.arns:
                    try:
                        # Validate ARN format using existing utility
                        build_resource_arn_object(arn)
                    except Exception as e:
                        raise ValueError(f"Invalid ARN '{arn}': {str(e)}")

    def _create_workload_data(self, name: str, regions: List[str]) -> WorkloadOnboard:
        """Create workload data object."""
        workload = WorkloadOnboard(
            support_case_id=None,
            name=name,
            regions=regions,
        )

        temp_submission = OnboardingSubmission(
            filehash="",
            schema_version="",
            idr_cli_version="",
            account_id="",
            status=OnboardingStatus.COMPLETED,
            created_at=datetime.now(timezone.utc),
            last_updated_at=datetime.now(timezone.utc),
            workload_onboard=workload,
        )
        display_workload_info_summary(self.ui, temp_submission)
        return workload

    def _discover_resources(
        self, discovery_config: DiscoveryConfig, regions: List[str]
    ) -> List[ResourceArn]:
        """Discover resources based on config."""
        if discovery_config.method == DiscoveryMethod.TAGS and discovery_config.tags:
            # Use existing utility for tag-based discovery
            tag_filters = [
                {"Key": k, "Values": [v]} for k, v in discovery_config.tags.items()
            ]
            tag_display = ", ".join(
                [f"{k}={v}" for k, v in discovery_config.tags.items()]
            )

            resources = self._input_resource_discovery._search_resources(
                tag_filters=tag_filters, tag_display=tag_display, regions=regions
            )

            if resources is None:
                return []

            # Extract ResourceArn objects from discovered resources
            resource_arns = []
            for resource in resources:
                if isinstance(resource, dict) and "ResourceArn" in resource:
                    resource_arn_obj = resource["ResourceArn"]
                    resource_arns.append(resource_arn_obj)

            return resource_arns

        elif discovery_config.method == DiscoveryMethod.ARNS and discovery_config.arns:
            self.ui.display_info(
                f"Using input ARNs: {len(discovery_config.arns)} specified"
            )

            resource_arns = []
            for arn_str in discovery_config.arns:
                resource_arn = build_resource_arn_object(arn_str)
                resource_arn.name = extract_resource_id_from_arn(arn_str)
                resource_arns.append(resource_arn)

            return resource_arns

        raise ValueError("No valid discovery method or data provided")

    def _create_submission(
        self,
        workload: WorkloadOnboard,
        resources: List[ResourceArn],
        account_id: str,
        progress_tracker: ProgressTracker,
        alarm_contacts: Optional[AlarmContacts] = None,
        status: OnboardingStatus = OnboardingStatus.COMPLETED,
    ) -> OnboardingSubmission:
        """Create onboarding submission object."""
        progress = CommandStatusTracker(workload_registration=progress_tracker)

        submission = OnboardingSubmission(
            filehash="",  # Will be calculated below
            schema_version=SCHEMA_VERSION,
            idr_cli_version=CLI_VERSION,
            account_id=account_id,
            status=status,
            created_at=datetime.now(timezone.utc),
            last_updated_at=datetime.now(timezone.utc),
            execution_mode=get_execution_mode(),
            workload_onboard=workload,
            alarm_contacts=alarm_contacts,
            resource_arns_selected=resources,
            progress=progress,
        )

        submission.filehash = calculate_submission_hash(submission)

        return submission

    def _handle_support_case_creation(
        self,
        session_id: str,
        dry_run_mode: bool,
    ) -> str:
        """Handle support case creation for both workload and alarm services.

        Returns:
            str: The created support case ID
        """
        if dry_run_mode:
            self.ui.display_info(
                "🔍 DRY RUN: Would create support case (skipping actual creation)",
                style="yellow",
            )
            return "DRY-RUN-CASE-ID"

        # Load session data into file cache service before support case creation
        file_path = self._file_cache_service.get_file_path(session_id)
        submission = self._file_cache_service.load_file_cache(file_path)
        if not submission:
            raise ValueError(f"Session data not found for session_id: {session_id}")

        # Set the loaded submission as the current file cache for both services
        self._file_cache_service.file_cache = submission
        self._support_case_service.file_cache_service.file_cache = submission

        self.ui.display_info("Creating support case...")
        case_id = self._support_case_service.create_case(session_id)
        self.ui.display_info(
            f"✅ A support case has been created. Display ID: {case_id}"
        )
        return str(case_id)

    def _create_filtered_json_output(
        self, submission: OnboardingSubmission
    ) -> Dict[str, Any]:
        """Create filtered JSON output for non-interactive commands by removing
        unnecessary fields."""
        # Convert submission to dict using existing method
        json_data = submission.to_dict()

        # Remove unnecessary fields for non-interactive JSON output
        unnecessary_fields = [
            "filehash",
            "progress",
            "progress_tracker",
            "workload_to_alarm_handoff",
            "alarm_validation",
            "resource_discovery_methods",
            "resource_tags",
        ]

        for field in unnecessary_fields:
            json_data.pop(field, None)

        return dict(json_data)

    @abstractmethod
    def execute_from_config(self, config: Dict[str, Any], account_id: str) -> Any:
        """Execute the service-specific operation from config data.

        This method should be implemented by child classes to handle their
        specific configuration and execution logic.
        """
        pass
