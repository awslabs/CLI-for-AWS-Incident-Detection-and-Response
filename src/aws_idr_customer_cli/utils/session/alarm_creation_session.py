from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast

from aws_idr_customer_cli.clients.iam import BotoIamManager
from aws_idr_customer_cli.exceptions import (
    AlarmCreationValidationError,
    AlarmIngestionValidationError,
    SupportCaseAlreadyExistsError,
    SupportCaseNotFoundError,
)
from aws_idr_customer_cli.input.input_resource_discovery import (
    InputResourceDiscovery,
)
from aws_idr_customer_cli.services.create_alarm.alarm_recommendation_service import (
    AlarmRecommendationService,
)
from aws_idr_customer_cli.services.create_alarm.alarm_service import AlarmService
from aws_idr_customer_cli.services.file_cache.data import AlarmCreation, AlarmIngestion
from aws_idr_customer_cli.services.file_cache.file_cache_service import (
    FileCacheService,
)
from aws_idr_customer_cli.services.support_case_service import SupportCaseService
from aws_idr_customer_cli.utils.alarm_contact_collection import (
    collect_alarm_contact_info,
    display_alarm_contact_summary,
    offer_alarm_contact_correction_workflow,
)
from aws_idr_customer_cli.utils.constants import CommandType
from aws_idr_customer_cli.utils.resource_discovery_utils import (
    discover_resources_by_tags,
    select_alarms,
    select_resources,
)
from aws_idr_customer_cli.utils.service_linked_role_utils import (
    check_and_create_service_linked_role,
)
from aws_idr_customer_cli.utils.session.interactive_session import (
    ACTION_BACK,
    ACTION_KEY,
    ACTION_QUIT,
    InteractiveSession,
    session_step,
)
from aws_idr_customer_cli.utils.session.session_store import SessionStore
from aws_idr_customer_cli.utils.support_case_utils import (
    handle_duplicate_support_case_interactive,
)
from aws_idr_customer_cli.utils.workload_meta_data_collection_utils import (
    collect_workload_info as utils_collect_workload_info,
)
from aws_idr_customer_cli.utils.workload_meta_data_collection_utils import (
    review_and_update_workload as utils_review_and_update_workload,
)

# SLR constant
SLR_ROLE_NAME = "AWSServiceRoleForHealth_EventProcessor"
SLR_SERVICE_NAME = "event-processor.health.amazonaws.com"


class AlarmCreationSession(InteractiveSession):
    """Alarm creation session"""

    def __init__(
        self,
        store: SessionStore,
        alarm_service: AlarmService,
        file_cache_service: FileCacheService,
        input_resource_discovery: InputResourceDiscovery,
        alarm_recommendation_service: AlarmRecommendationService,
        support_case_service: SupportCaseService,
        iam_manager: BotoIamManager,
        account_id: str = "123456789012",  # placeholder
        resume_session_id: Optional[str] = None,
    ) -> None:
        super().__init__(
            CommandType.ALARM_CREATION, account_id, store, resume_session_id
        )

        if resume_session_id:
            if (
                getattr(self, "current_step", 0) == 0
                and self.submission
                and self.submission.workload_onboard
                and getattr(self.submission.workload_onboard, "support_case_id", None)
            ):
                self.current_step = 2

        self.alarm_service = alarm_service
        self.file_cache_service = file_cache_service
        self.input_resource_discovery = input_resource_discovery
        self.alarm_recommendation_service = alarm_recommendation_service
        self.support_case_service = support_case_service
        self._iam_manager = iam_manager

    @staticmethod
    def pluralize(count: int) -> str:
        return "alarm" if count == 1 else "alarms"

    def _display_alarm_creation_result(
        self, results: Dict[str, List[AlarmCreation]]
    ) -> None:
        """Display alarm creation results summary with proper error handling."""
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
                    f"  • {created_count} new {self.pluralize(created_count)} "
                    f"created successfully ✅"
                )

            if existing_count > 0:
                self.ui.display_info(
                    f"  • {existing_count} selected {self.pluralize(existing_count)} "
                    f"already exist in CloudWatch ✅"
                )

            if failed_count > 0:
                self.ui.display_error(
                    f"  • {failed_count} {self.pluralize(failed_count)} "
                    f"failed to create ❌"
                )

            if unselected_count > 0:
                self.ui.display_info(
                    f"  • {unselected_count} {self.pluralize(unselected_count)} "
                    f"not selected (skipped as expected)"
                )

            self.ui.display_info("")

            # Overall summary
            total_ready = created_count + existing_count
            if failed_count > 0:
                if total_ready > 0:
                    self.ui.display_warning(
                        f"⚠️  {total_ready} {self.pluralize(total_ready)} ready for "
                        f"integration, but {failed_count} failed"
                    )
                else:
                    self.ui.display_error(
                        f"❌ No alarms ready - all {failed_count} selected "
                        f"{self.pluralize(failed_count)} failed to create"
                    )
            elif total_ready > 0:
                self.ui.display_info(
                    f"✅ All {total_ready} selected {self.pluralize(total_ready)} "
                    f"ready for incident response integration"
                )
            else:
                self.ui.display_info("ℹ️  No alarms were selected for creation")

        except Exception as e:
            # Graceful error handling
            self.ui.display_error("❌ Unable to display alarm creation summary")
            raise RuntimeError(f"Error displaying alarm results: {e}") from e

    def _display_resume_info(self) -> None:
        pass

    def _display_support_case(self, support_case_id: str) -> None:
        """Display support case information."""
        try:
            case = self.support_case_service.describe_case(support_case_id)
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

    def _display_cached_resources_summary(self) -> None:
        """Display a summary of current cached resources grouped by type."""
        if self.submission and self.submission.resource_arns_selected:
            cached_resources = self.submission.resource_arns_selected
            resource_count = len(cached_resources)

            # Group resources by type
            resource_summary = {}
            region_summary = set()

            for resource in cached_resources:
                resource_type = resource.type
                region_summary.add(resource.region)

                if resource_type not in resource_summary:
                    resource_summary[resource_type] = 0
                resource_summary[resource_type] += 1

            self.ui.display_info(
                f"📋 Current saved workload resources ({resource_count} total):"
            )

            # Display resource type summary
            for resource_type, count in sorted(resource_summary.items()):
                self.ui.display_info(f"  • {resource_type}: {count} resource(s)")

            # Display regions
            regions_str = ", ".join(sorted(region_summary))
            self.ui.display_info(f"  • Regions: {regions_str}")
            self.ui.display_info("")  # Add spacing
        else:
            self.ui.display_info("📋 No cached resources found")
            self.ui.display_info("")  # Add spacing

    @session_step("Collect Workload Metadata", order=1)
    def _collect_workload_info(self) -> Dict[str, Any]:
        """Collect basic workload information."""
        return cast(
            Dict[str, Any],
            utils_collect_workload_info(self.ui, self.submission, self._save_progress),
        )

    @session_step("Review and Update Workload Information", order=2)
    def _review_and_update_workload(self) -> Dict[str, Any]:
        """Review and update workload information with correction workflow."""
        return cast(
            Dict[str, Any],
            utils_review_and_update_workload(
                self.ui, self.submission, self._save_progress
            ),
        )

    @session_step("Collect Alarm Contact Information", order=3)
    def _collect_contact_info(self) -> Dict[str, Any]:
        """Collect contact information for alarm notifications."""
        self.ui.display_info(
            (
                "📞 Collecting primary and escalation contacts for when an alarm "
                "triggers for this workload. "
                "AWS will engage alarm contacts via AWS Support Case. "
            )
        )
        self.ui.display_info(
            "💡 You can review and update contact information in the next step"
        )

        if not collect_alarm_contact_info(self.ui, self.submission):
            return {ACTION_KEY: ACTION_BACK}

        display_alarm_contact_summary(self.ui, self.submission)
        return {}

    @session_step("Review and Update Contact Information", order=4)
    def _review_and_update_contacts(self) -> Dict[str, Any]:
        """Review and update contact information with correction workflow."""

        # Display current contact information
        display_alarm_contact_summary(self.ui, self.submission)

        # Offer correction workflow until satisfied
        while offer_alarm_contact_correction_workflow(self.ui, self.submission):
            display_alarm_contact_summary(self.ui, self.submission)

        self.ui.display_info("✅ Alarm contact information finalized")
        return {}

    @session_step("Select Resource Discovery Method", order=5)
    def _select_discovery_method(self) -> Dict[str, Any]:
        """Select how to get resources for alarm creation."""
        if not (
            self.submission.workload_onboard
            and getattr(self.submission.workload_onboard, "support_case_id", None)
        ):
            self.current_step = 4
            return {}
        self._display_cached_resources_summary()

        methods = [
            "Use saved workload resources",
            "Re-discover and update resources using tags",
        ]

        choice = self.ui.select_option(
            methods, "How would you like to get resources for alarm creation?"
        )

        if choice == 0:
            self.ui.display_info(
                "✅ Selected: Use saved resources from workload ingestion step"
            )
            self.current_step = 6
        else:
            self.ui.display_info("✅ Selected: Discover resources through tags")
            self.current_step = 4

        return {}

    @session_step("Discover Eligible Resources", order=6)
    def discover_resources(self) -> Dict[str, str]:
        """Execute resource discovery using input handler."""
        regions = (
            self.submission.workload_onboard.regions
            if self.submission.workload_onboard
            else ["us-east-1"]
        )

        result = discover_resources_by_tags(self.input_resource_discovery, regions)

        # Handle navigation action
        if isinstance(result, dict):
            return result

        # Extract resources and tags from tuple result
        resources, tag_filters = result

        # Store resources and tags in submission
        if not self.submission:
            raise RuntimeError("No submission available")
        self.submission.resource_arns_selected = resources
        self.submission.resource_tags = tag_filters

        resource_count = len(resources)
        self.ui.display_info(
            message=f"✅ Discovered {resource_count} eligible resources for all given regions",
        )
        self.ui.display_info(
            message="ℹ️  Resources not eligible for monitoring like IAM roles, security "
            "groups, and subnets are excluded",
            style="dim",
        )
        return {}

    @session_step("Select Resources", order=7)
    def select_resources(self) -> Dict[str, str]:
        """Select resources for alarm creation."""
        if not self.submission or not self.submission.resource_arns_selected:
            self.ui.display_warning(
                "No resources were discovered. Returning to resource discovery."
            )
            return {ACTION_KEY: ACTION_BACK}

        result = select_resources(
            ui=self.ui,
            resource_arns=self.submission.resource_arns_selected,
            message_header="Alarm Resource Selection",
            main_message="Select resources for alarm creation",
            item_attribute_name="resource",
        )

        # Handle navigation action
        if isinstance(result, dict):
            return result

        # Update submission directly
        self.submission.resource_arns_selected = result
        return {}

    @session_step("Alarm Selection", order=8)
    def _select_alarms(self) -> Dict[str, Any]:
        """Prepare alarm information from discovered resources."""
        resources = self.submission.resource_arns_selected

        if not resources:
            self.ui.display_warning(
                "No resources available for alarm creation. Returning to resource selection."
            )
            return {ACTION_KEY: ACTION_BACK}

        alarm_recommendations = self.alarm_service.generate_alarm_recommendations(
            resources
        )

        if not alarm_recommendations:
            self.ui.display_warning(
                "No alarm recommendations could be generated from the selected resources. "
                "Returning to resource selection."
            )
            return {ACTION_KEY: ACTION_BACK}

        result = select_alarms(
            ui=self.ui,
            alarm_recommendations=alarm_recommendations,
            message_header="Alarm Creation Selection",
            main_message="Select alarms for creation",
        )

        self.ui.display_info("🔄 Processing selected alarms for creation...")

        # Handle navigation action
        if isinstance(result, dict):
            return result

        self.submission.alarm_creation = (
            self.alarm_service.recommendations_to_alarm_creation_objects(result)
        )
        return {}

    @session_step("Create Alarms", order=9)
    def _create_alarms(self) -> Dict[str, Any]:
        alarms = self.submission.alarm_creation or []

        alarms_to_create_count = len(
            [alarm for alarm in alarms if alarm.is_selected is True]
        )

        confirmed = self.ui.prompt_confirm(
            f"Are you ready to proceed with creating these {alarms_to_create_count} alarms?"
        )

        if not confirmed:
            self.ui.display_warning(
                "Alarm creation declined. Returning to alarm selection"
            )
            return {ACTION_KEY: ACTION_BACK}

        recommendations = self.alarm_service.alarm_creation_objects_to_recommendations(
            alarms
        )

        results = self.alarm_service.create_alarms_from_recommendations(recommendations)
        self.submission.alarm_creation = (
            results.get("created_alarms", [])
            + results.get("existing_alarms", [])
            + results.get("failed_alarms", [])
            + results.get("unselected_alarms", [])
        )
        self._display_alarm_creation_result(results=results)
        return {}

    @session_step("Confirm Alarm Ingestion", order=10)
    def _confirm_alarm_ingestion(self) -> Dict[str, Any]:
        """Present confirmation summary and get customer approval for alarm ingestion."""
        alarm_creations = self.submission.alarm_creation or []

        created_count = len([alarm for alarm in alarm_creations if alarm.successful])
        existing_count = len(
            [
                alarm
                for alarm in alarm_creations
                if alarm.is_selected and alarm.already_exists
            ]
        )
        onboard_alarms = [
            alarm
            for alarm in alarm_creations
            if alarm.successful or (alarm.is_selected and alarm.already_exists)
        ]

        total_alarms = created_count + existing_count
        alarm_word = "alarms" if total_alarms > 1 else "alarm"
        self.ui.display_info(
            f"📋 Ready to onboard {total_alarms} CloudWatch {alarm_word} "
            f"to the IDR system using your contact information below."
        )

        display_alarm_contact_summary(self.ui, self.submission)

        confirmed = self.ui.prompt_confirm(
            f'Proceed with onboarding {"this" if total_alarms <= 1 else "these"} '
            f"{total_alarms} {alarm_word} to IDR? [y/n] (y):"
        )

        if confirmed:
            # Initialize alarm_ingestion if needed
            if not self.submission.alarm_ingestion:
                self.submission.alarm_ingestion = AlarmIngestion(
                    onboarding_alarms=[],
                    contacts_approval_timestamp=datetime.now(timezone.utc),
                )
            self.submission.alarm_ingestion.onboarding_alarms.extend(
                self.alarm_service.convert_created_alarms_to_onboarding_alarms(
                    onboard_alarms, self.submission.alarm_contacts
                )
            )
            self.submission.alarm_ingestion.contacts_approval_timestamp = datetime.now(
                timezone.utc
            )

            self.ui.display_info("✅ Alarms successfully submitted for IDR onboarding!")
            return {}
        else:
            self.ui.display_info("❌ Alarm ingestion cancelled")
            self.ui.display_info(
                "💡 Please restart the alarm-creation process to make changes"
            )
            return {ACTION_KEY: ACTION_QUIT}

    # This step must be executed last
    @session_step("Working on the Support Case", order=11)
    def handle_support_case(self) -> Dict[str, Any]:
        case_id = self._get_existing_support_case_id()
        if case_id:
            try:
                updated_case_id = (
                    self.support_case_service.update_case_with_attachment_set(
                        session_id=self.session_id, case_id=case_id
                    )
                )
                if updated_case_id:
                    self.ui.display_info("✅ Support case has been updated")
                    self._display_support_case(updated_case_id)
                    return {}
                else:
                    # Case was resolved, fall through to create new case
                    self.ui.display_info(
                        f"ℹ️  Previous support case {case_id} is resolved. "
                        "Creating a new support case..."
                    )
            except (AlarmCreationValidationError, AlarmIngestionValidationError) as e:
                self.ui.display_info(str(e))
                return {}

        # Create new case (either no existing case or previous case was resolved)
        try:
            case_id = self.support_case_service.create_case(self.session_id)
            self.submission.workload_onboard.support_case_id = case_id
            self.ui.display_info("✅ Support case has been created")
            self._display_support_case(case_id)
        except SupportCaseAlreadyExistsError as e:
            case_id = handle_duplicate_support_case_interactive(
                ui=self.ui,
                support_case_service=self.support_case_service,
                session_id=self.session_id,
                error=e,
                workload_name=self.submission.workload_onboard.name,
                update_prompt="Would you like to update it with your new alarms?",
                display_case_callback=self._display_support_case,
            )

            if case_id:
                self.submission.workload_onboard.support_case_id = case_id

        return {}

    @session_step("Check Service Linked Role", order=12)
    def _check_service_linked_role(self) -> Dict[str, Any]:
        """Check if Service Linked Role exists and prompt to create if needed."""

        result: Dict[str, Any] = check_and_create_service_linked_role(
            self.ui, self._iam_manager
        )
        return result

    def _get_existing_support_case_id(self) -> Optional[str]:
        """Session method to get case ID from its own data."""
        if (
            self.submission
            and self.submission.workload_onboard
            and self.submission.workload_onboard.support_case_id
        ):
            return cast(str, self.submission.workload_onboard.support_case_id)
        return None
