"""Refactored service for non-interactive alarm creation."""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast

from injector import inject

from aws_idr_customer_cli.clients.iam import BotoIamManager
from aws_idr_customer_cli.core.interactive.ui import InteractiveUI
from aws_idr_customer_cli.exceptions import SupportCaseAlreadyExistsError
from aws_idr_customer_cli.input.input_resource_discovery import InputResourceDiscovery
from aws_idr_customer_cli.models.alarm_models import AlarmRecommendation
from aws_idr_customer_cli.models.non_interactive_config import (
    AlarmContactsConfig,
    AlarmCreationConfig,
    AlarmSelectionConfig,
    OutputFormat,
)
from aws_idr_customer_cli.services.create_alarm.alarm_service import AlarmService
from aws_idr_customer_cli.services.file_cache.data import (
    AlarmContacts,
    AlarmIngestion,
    ContactInfo,
    OnboardingStatus,
    OnboardingSubmission,
    ProgressTracker,
)
from aws_idr_customer_cli.services.file_cache.file_cache_service import FileCacheService
from aws_idr_customer_cli.services.non_interactive_base_service import (
    NonInteractiveServiceBase,
)
from aws_idr_customer_cli.services.support_case_service import SupportCaseService
from aws_idr_customer_cli.utils.alarm_contact_collection import (
    display_alarm_contact_summary,
)
from aws_idr_customer_cli.utils.constants import CLI_VERSION, SCHEMA_VERSION
from aws_idr_customer_cli.utils.execution_mode import (
    ExecutionMode,
)
from aws_idr_customer_cli.utils.resource_discovery_utils import (
    display_selected_resources,
)
from aws_idr_customer_cli.utils.session.alarm_creation_session import (
    SLR_ROLE_NAME,
    SLR_SERVICE_NAME,
)
from aws_idr_customer_cli.utils.session.session_store import SessionStore
from aws_idr_customer_cli.utils.support_case_utils import extract_case_id_from_error
from aws_idr_customer_cli.utils.validation.validator import Validate


class NonInteractiveAlarmService(NonInteractiveServiceBase):
    """Service for non-interactive alarm creation."""

    @inject
    def __init__(
        self,
        ui: InteractiveUI,
        store: SessionStore,
        input_resource_discovery: InputResourceDiscovery,
        validator: Validate,
        support_case_service: SupportCaseService,
        file_cache_service: FileCacheService,
        alarm_service: AlarmService,
        iam_manager: BotoIamManager,
    ) -> None:
        super().__init__(
            ui=ui,
            store=store,
            input_resource_discovery=input_resource_discovery,
            validator=validator,
            support_case_service=support_case_service,
            file_cache_service=file_cache_service,
        )
        self._alarm_service = alarm_service
        self._iam_manager = iam_manager

    def _display_dry_run_specific_info(self) -> None:
        """Display dry run info specific to alarm creation."""
        self.ui.display_info(
            "Alarm creation, support case creation, and service-linked role "
            "creation will be skipped",
            style="yellow",
        )

    def _create_alarm_contact_data(
        self, contacts_config: AlarmContactsConfig
    ) -> AlarmContacts:
        """Create alarm contact information from config."""
        primary_contact = ContactInfo(
            name=contacts_config.primary.name,
            email=contacts_config.primary.email,
            phone=contacts_config.primary.phone or "",
        )

        escalation_contact = (
            ContactInfo(
                name=contacts_config.escalation.name,
                email=contacts_config.escalation.email,
                phone=contacts_config.escalation.phone or "",
            )
            if contacts_config.escalation
            else primary_contact
        )

        contacts = AlarmContacts(
            primary_contact=primary_contact, escalation_contact=escalation_contact
        )

        return contacts

    def create_alarms_from_config(
        self, config: Dict[str, Any], account_id: str
    ) -> None:
        """Execute complete alarm creation from config data."""
        config_obj = AlarmCreationConfig.from_dict(config)
        json_output = {}
        try:
            submission = self.execute_from_config(config, account_id)
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
        self, config: Dict[str, Any], account_id: str
    ) -> OnboardingSubmission:
        """Execute alarm creation from config data using existing services."""
        config_obj = AlarmCreationConfig.from_dict(config)

        # Set output format from config
        self.set_output_format(config_obj.options.output_format)
        dry_run_mode = config_obj.options.dry_run

        if dry_run_mode:
            self._display_dry_run_header()

        self.validate_config(
            workload_name=config_obj.workload.name,
            workload_regions=config_obj.workload.regions,
            alarm_contacts_config=config_obj.contacts,
            discovery_config=config_obj.discovery,
        )

        workload = self._create_workload_data(
            name=config_obj.workload.name,
            regions=config_obj.workload.regions,
        )
        alarm_contacts = self._create_alarm_contact_data(config_obj.contacts)

        # Create temporary submission to display contact summary
        current_time = datetime.now(timezone.utc)
        temp_submission = OnboardingSubmission(
            filehash="",
            schema_version=SCHEMA_VERSION,
            idr_cli_version=CLI_VERSION,
            account_id=account_id,
            status=OnboardingStatus.IN_PROGRESS,
            created_at=current_time,
            last_updated_at=current_time,
            alarm_contacts=alarm_contacts,
        )
        display_alarm_contact_summary(self.ui, temp_submission)

        self.ui.display_info(
            f"Starting resource discovery using method: {config_obj.discovery.method.value}"
        )
        resources = self._discover_resources(
            config_obj.discovery, config_obj.workload.regions
        )
        self.ui.display_info(f"✅ Discovered {len(resources)} resources", style="green")

        submission = self._create_submission(
            workload=workload,
            resources=resources,
            account_id=account_id,
            progress_tracker=self._create_alarm_progress_tracker(),
            alarm_contacts=alarm_contacts,
        )

        submission.execution_mode = ExecutionMode.NON_INTERACTIVE

        session_id = self.store.create(submission)

        display_selected_resources(self.ui, resources)

        # Generate and select alarms (delegating to AlarmService)
        alarm_recommendations = self._alarm_service.generate_alarm_recommendations(
            resources
        )
        self.ui.display_info(
            f"Generated {len(alarm_recommendations)} alarm recommendations"
        )

        if not alarm_recommendations:
            self.ui.display_warning("No alarm recommendations generated")
            return submission

        # Filter alarms based on selection config (simplified)
        selected_alarms = self._filter_alarms_by_resource_types(
            alarm_recommendations, config_obj.alarm_selection
        )
        self.ui.display_info(
            f"✅ Selected {len(selected_alarms)} alarms for creation", style="green"
        )

        # Create alarms (delegating to AlarmService)
        if dry_run_mode:
            creation_results = self._simulate_alarm_creation(selected_alarms)
        else:
            creation_results = self._alarm_service.create_alarms_from_recommendations(
                selected_alarms
            )

        # Update submission with results
        submission.alarm_creation = (
            creation_results.get("created_alarms", [])
            + creation_results.get("existing_alarms", [])
            + creation_results.get("failed_alarms", [])
            + creation_results.get("unselected_alarms", [])
        )

        # Handle alarm ingestion (delegating to AlarmService)
        self._handle_alarm_ingestion_simplified(
            submission, creation_results, dry_run_mode
        )

        # Update file cache BEFORE creating support case so attachment has alarm data
        self.store.update(session_id, submission)

        # Handle support case (using base class method with error handling)
        case_id = None
        if config_obj.options.create_support_case:
            case_id = self._handle_support_case_with_duplicate_handling(
                submission, session_id, config_obj, dry_run_mode
            )

        # Handle service linked role (extracted to utility method)
        slr_created = False
        if config_obj.options.create_service_linked_role:
            slr_created = self._handle_service_linked_role(dry_run_mode)

        # Final update to save support case ID if it was created
        self.store.update(session_id, submission)

        # Display summary
        self._display_final_summary(creation_results, submission, case_id, slr_created)

        return submission

    def _create_alarm_progress_tracker(self) -> ProgressTracker:
        """Create progress tracker for alarm creation."""
        return ProgressTracker(
            current_step=8,  # Alarm creation complete
            total_steps=12,
            step_name="alarm_creation_completed",
            completed_steps=[
                "workload_info",
                "contacts",
                "discovery",
                "selection",
                "alarm_selection",
                "alarm_creation",
            ],
        )

    def _filter_alarms_by_resource_types(
        self,
        alarm_recommendations: List[AlarmRecommendation],
        selection_config: AlarmSelectionConfig,
    ) -> List[AlarmRecommendation]:
        """Filter alarms by resource types (simplified from original)."""
        if not selection_config.resource_types:
            return alarm_recommendations

        self.ui.display_info(
            f"Filtering alarms by resource types: {selection_config.resource_types}"
        )
        filtered_alarms = []
        for alarm in alarm_recommendations:
            alarm_name = getattr(alarm, "alarm_name", "")
            for resource_type in selection_config.resource_types:
                if resource_type.lower() in alarm_name.lower():
                    filtered_alarms.append(alarm)
                    break

        self.ui.display_info(
            f"Selected {len(filtered_alarms)} out of {len(alarm_recommendations)} alarms"
        )
        return filtered_alarms

    def _simulate_alarm_creation(
        self, selected_alarms: List[AlarmRecommendation]
    ) -> Dict[str, Any]:
        """Simulate alarm creation for dry run mode."""
        self.ui.display_info(
            "🔍 DRY RUN: Would create the following alarms:", style="yellow"
        )
        for alarm in selected_alarms:
            alarm_name = getattr(alarm, "alarm_name", "Unknown")
            resource_arn = getattr(alarm, "resource_arn", None)
            resource_str = resource_arn.arn if resource_arn else "unknown"
            self.ui.display_info(f"  • {alarm_name} (Resource: {resource_str})")

        # Convert to AlarmCreation objects for consistency
        dry_run_alarms = self._alarm_service.recommendations_to_alarm_creation_objects(
            selected_alarms
        )
        for alarm in dry_run_alarms:
            alarm.successful = True
            alarm.created_at = datetime.now(timezone.utc)

        self.ui.display_info(
            f"🔍 DRY RUN Summary: Would create {len(selected_alarms)} alarms",
            style="yellow",
        )
        return {
            "created_alarms": dry_run_alarms,
            "existing_alarms": [],
            "failed_alarms": [],
            "unselected_alarms": [],
        }

    def _display_alarm_creation_result(self, results: Dict[str, Any]) -> None:
        """Display alarm creation results summary with proper error handling.

        Reused from AlarmCreationSession to provide consistent UI experience.
        """
        try:
            # Calculate counts safely
            created_count = len(results.get("created_alarms", []))
            existing_count = len(results.get("existing_alarms", []))
            failed_count = len(results.get("failed_alarms", []))
            unselected_count = len(results.get("unselected_alarms", []))

            self.ui.display_info("📊 Alarm Creation Summary:")

            # Display results with proper pluralization
            if created_count > 0:
                self.ui.display_info(
                    f"  • {created_count} new {self._pluralize_alarm(created_count)} "
                    f"created successfully ✅"
                )

            if existing_count > 0:
                self.ui.display_info(
                    f"  • {existing_count} selected {self._pluralize_alarm(existing_count)} "
                    f"already exist in CloudWatch ✅"
                )

            if failed_count > 0:
                self.ui.display_error(
                    f"  • {failed_count} {self._pluralize_alarm(failed_count)} "
                    f"failed to create ❌"
                )

            if unselected_count > 0:
                self.ui.display_info(
                    f"  • {unselected_count} {self._pluralize_alarm(unselected_count)} "
                    f"not selected (skipped as expected)"
                )

            self.ui.display_info("")

            # Overall summary
            total_ready = created_count + existing_count
            if failed_count > 0:
                if total_ready > 0:
                    self.ui.display_warning(
                        f"⚠️  {total_ready} {self._pluralize_alarm(total_ready)} ready for "
                        f"integration, but {failed_count} failed"
                    )
                else:
                    self.ui.display_error(
                        f"❌ No alarms ready - all {failed_count} selected "
                        f"{self._pluralize_alarm(failed_count)} failed to create"
                    )
            elif total_ready > 0:
                self.ui.display_info(
                    f"✅ All {total_ready} selected {self._pluralize_alarm(total_ready)} "
                    f"ready for incident response integration"
                )
            else:
                self.ui.display_info("ℹ️  No alarms were selected for creation")

        except Exception as e:
            # Graceful error handling
            self.ui.display_error("❌ Unable to display alarm creation summary")
            raise RuntimeError(f"Error displaying alarm results: {e}") from e

    def _pluralize_alarm(self, count: int) -> str:
        """Helper method for alarm pluralization."""
        return "alarm" if count == 1 else "alarms"

    def _display_specific_alarms_list(self, creation_results: Dict[str, Any]) -> None:
        """Display the specific alarms being processed."""
        all_alarms = []
        all_alarms.extend(creation_results.get("created_alarms", []))
        all_alarms.extend(creation_results.get("existing_alarms", []))
        all_alarms.extend(creation_results.get("failed_alarms", []))

        if all_alarms:
            self.ui.display_info("📝 Alarm Details:")

            for alarm in all_alarms:
                alarm_name = getattr(alarm, "alarm_configuration", None)
                if alarm_name:
                    alarm_name = getattr(alarm_name, "alarm_name", "Unknown")
                else:
                    alarm_name = "Unknown"

                resource_arn = getattr(alarm, "resource_arn", None)
                if resource_arn:
                    resource_info = f"{resource_arn.type} ({resource_arn.region})"
                else:
                    resource_info = "Unknown resource"

                # Determine status
                if hasattr(alarm, "successful") and alarm.successful is True:
                    status = "✅ Created"
                elif hasattr(alarm, "already_exists") and alarm.already_exists:
                    status = "✅ Already exists"
                elif hasattr(alarm, "successful") and alarm.successful is False:
                    status = "❌ Failed"
                else:
                    status = "⏭️  Skipped"

                self.ui.display_info(f"   • {alarm_name} - {resource_info} - {status}")

            self.ui.display_info("")

    def _handle_alarm_ingestion_simplified(
        self,
        submission: OnboardingSubmission,
        creation_results: Dict[str, Any],
        dry_run_mode: bool = False,
    ) -> None:
        """Handle alarm ingestion using AlarmService."""
        if not dry_run_mode:
            self._display_alarm_creation_result(creation_results)
            self._display_specific_alarms_list(creation_results)

        created_alarms = creation_results.get("created_alarms", [])
        existing_alarms = creation_results.get("existing_alarms", [])
        onboard_alarms = created_alarms + [
            alarm for alarm in existing_alarms if getattr(alarm, "is_selected", True)
        ]

        if onboard_alarms:
            if not submission.alarm_ingestion:
                submission.alarm_ingestion = AlarmIngestion(
                    onboarding_alarms=[],
                    contacts_approval_timestamp=datetime.now(timezone.utc),
                )

            # Delegate to AlarmService for conversion
            submission.alarm_ingestion.onboarding_alarms.extend(
                self._alarm_service.convert_created_alarms_to_onboarding_alarms(
                    onboard_alarms, submission.alarm_contacts
                )
            )
            submission.alarm_ingestion.contacts_approval_timestamp = datetime.now(
                timezone.utc
            )

            self.ui.display_info(
                f"✅ Processed {len(onboard_alarms)} alarms for ingestion",
                style="green",
            )
        else:
            self.ui.display_info("No alarms available for ingestion", level="warning")

    def _handle_support_case_with_duplicate_handling(
        self,
        submission: OnboardingSubmission,
        session_id: str,
        config_obj: AlarmCreationConfig,
        dry_run_mode: bool,
    ) -> Optional[str]:
        """Handle support case creation with duplicate detection."""
        try:
            return str(self._handle_support_case_creation(session_id, dry_run_mode))
        except SupportCaseAlreadyExistsError as e:
            if config_obj.options.update_existing_case:
                existing_case_id = extract_case_id_from_error(str(e))
                if existing_case_id:
                    self.ui.display_info(f"Updating existing case: {existing_case_id}")
                    self._file_cache_service.file_cache = submission
                    self._support_case_service.file_cache_service.file_cache = (
                        submission
                    )
                    self._support_case_service.update_case_with_attachment_set(
                        session_id=session_id, case_id=existing_case_id
                    )
                    if submission.workload_onboard:
                        submission.workload_onboard.support_case_id = existing_case_id
                    self.ui.display_info(
                        "✅ Support case updated successfully", style="green"
                    )
                    return cast(str, existing_case_id)
            return None

    def _handle_service_linked_role(self, dry_run_mode: bool = False) -> bool:
        """Handle service linked role creation (extracted from AlarmCreationSession)."""
        if dry_run_mode:
            self.ui.display_info(
                "🔍 DRY RUN: Would check and create service-linked role", style="yellow"
            )
            return True

        try:
            self.ui.display_info("Checking Service Linked Role for IDR")

            if self._iam_manager.service_linked_role_exists(SLR_ROLE_NAME):
                self.ui.display_info(
                    "✅ Service Linked Role already exists", style="green"
                )
                return False

            self.ui.display_info("Creating Service Linked Role for IDR")
            role_name = self._iam_manager.create_service_linked_role(SLR_SERVICE_NAME)
            self.ui.display_info(
                f"✅ Created Service Linked Role: {role_name}", style="green"
            )
            return True

        except Exception as e:
            self.ui.display_warning(f"Service Linked Role handling failed: {e}")
            return False

    def _display_final_summary(
        self,
        creation_results: Dict[str, Any],
        submission: OnboardingSubmission,
        case_id: Optional[str],
        slr_created: bool,
    ) -> None:
        """Display final summary of alarm creation."""
        created_count = len(creation_results.get("created_alarms", []))
        existing_count = len(creation_results.get("existing_alarms", []))
        failed_count = len(creation_results.get("failed_alarms", []))

        # Final completion status
        if failed_count > 0:
            if created_count > 0 or existing_count > 0:
                self.ui.display_warning(
                    "⚠️  Alarm creation completed with some failures", style="yellow"
                )
            else:
                self.ui.display_error("❌ Alarm creation failed", style="red")
        else:
            self.ui.display_info(
                "✅ Alarm creation completed successfully", style="green"
            )

        summary_data = {
            "Workload name": (
                submission.workload_onboard.name
                if submission.workload_onboard
                else "Unknown"
            ),
            "Resources processed": str(len(submission.resource_arns_selected or [])),
            "Alarms created": str(created_count),
            "Alarms existing": str(existing_count),
            "Alarms failed": str(failed_count),
            "Support case ID": case_id or "None",
            "Service linked role created": "Yes" if slr_created else "No",
        }

        self.ui.display_result("📋 Alarm creation summary", summary_data)
