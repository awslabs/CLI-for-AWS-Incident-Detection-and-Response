from datetime import datetime, timezone
from typing import Any, Dict, Optional, cast

from aws_idr_customer_cli.services.create_alarm.alarm_service import AlarmService
from aws_idr_customer_cli.services.file_cache.data import (
    AlarmConfiguration,
    AlarmCreation,
    AlarmIngestion,
    AlarmValidation,
)
from aws_idr_customer_cli.utils.alarm_contact_collection import (
    collect_alarm_contact_info,
    display_alarm_contact_summary,
    offer_alarm_contact_correction_workflow,
)
from aws_idr_customer_cli.utils.arn_utils import build_resource_arn_object
from aws_idr_customer_cli.utils.constants import (
    DEFAULT_REGION,
    AlarmInputMethod,
    CommandType,
)
from aws_idr_customer_cli.utils.resource_discovery_utils import (
    collect_manual_alarm_arns,
    select_cloudwatch_alarms,
)
from aws_idr_customer_cli.utils.service_linked_role_utils import (
    check_and_create_service_linked_role,
)
from aws_idr_customer_cli.utils.session.interactive_session import (
    ACTION_BACK,
    ACTION_KEY,
    InteractiveSession,
    session_step,
)
from aws_idr_customer_cli.utils.validate_alarm.alarm_validator import AlarmValidator
from aws_idr_customer_cli.utils.workload_meta_data_collection_utils import (
    collect_workload_info as utils_collect_workload_info,
)
from aws_idr_customer_cli.utils.workload_meta_data_collection_utils import (
    review_and_update_workload as utils_review_and_update_workload,
)


class AlarmIngestionSession(InteractiveSession):
    """Alarm ingestion session."""

    def __init__(
        self,
        store: Any,
        input_resource_discovery: Any,
        validator: Any,
        comprehensive_validator: AlarmValidator,
        support_case_service: Any,
        iam_manager: Any,
        alarm_service: AlarmService,
        account_id: str = "123456789012",
        resume_session_id: Optional[str] = None,
    ):
        super().__init__(
            CommandType.ALARM_INGESTION,
            account_id,
            store,
            resume_session_id,
        )
        self.input_resource_discovery = input_resource_discovery
        self.validator = validator
        self.comprehensive_validator = comprehensive_validator
        self.support_case_service = support_case_service
        self._iam_manager = iam_manager
        self.alarm_service = alarm_service

    def _display_resume_info(self) -> None:
        pass

    @session_step("Collect Workload Metadata", order=1)
    def _collect_workload_info(self) -> Dict[str, Any]:
        """Collect basic workload information (name only, regions asked later if needed)."""
        return cast(
            Dict[str, Any],
            utils_collect_workload_info(
                self.ui, self.submission, self._save_progress, skip_regions=True
            ),
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
                "📞 Collecting contact details of your company's internal major "
                "incident / IT crisis management team."
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

    @session_step("Select Input Method", order=5)
    def _select_input_method(self) -> Dict[str, str]:
        """Select how to provide alarm ARNs for ingestion."""
        self.ui.display_info("🔍 CloudWatch Alarm Ingestion")
        self.ui.display_info("")
        self.ui.display_info("How would you like to provide alarm ARNs?")

        options = [
            "Find alarms by tags",
            "Upload a text file with ARNs",
            "Enter ARNs manually",
        ]

        choice = self.ui.select_option(options, "Select input method")

        if choice == 0:
            self.submission.input_method = AlarmInputMethod.TAGS
        elif choice == 1:
            self.submission.input_method = AlarmInputMethod.FILE
        elif choice == 2:
            self.submission.input_method = AlarmInputMethod.MANUAL
        else:
            return {ACTION_KEY: ACTION_BACK}

        return {}

    @session_step("Discover Alarms", order=6)
    def _discover_alarms(self) -> Dict[str, str]:
        """Discover or collect alarm ARNs based on selected method."""
        input_method = getattr(self.submission, "input_method", AlarmInputMethod.TAGS)

        if input_method == AlarmInputMethod.TAGS:
            # Ask for regions only for tag-based discovery
            if (
                not self.submission.workload_onboard
                or not self.submission.workload_onboard.regions
            ):
                self.ui.display_info("📍 Select regions to search for alarms")
                from aws_idr_customer_cli.utils.workload_meta_data_collection_utils import (
                    collect_regions,
                )

                regions = collect_regions(self.ui)
                if not regions:
                    # Use default if user doesn't provide any
                    regions = [DEFAULT_REGION]

                if self.submission.workload_onboard:
                    self.submission.workload_onboard.regions = regions
            else:
                regions = self.submission.workload_onboard.regions

            result = self.input_resource_discovery.discover_alarms_by_tags(
                regions=regions
            )

            if isinstance(result, dict):
                return result

            alarm_arns, tag_filters = result
            self.submission.alarm_arns = alarm_arns
            alarm_count = len(alarm_arns)
            self.ui.display_info(
                f"✅ Found {alarm_count} alarm(s) matching tag criteria"
            )

        elif input_method in [AlarmInputMethod.FILE, AlarmInputMethod.MANUAL]:
            # For file/manual input, regions are extracted from ARNs
            result = collect_manual_alarm_arns(
                ui=self.ui,
                validator=self.validator,
                input_method=str(input_method.value),
            )

            if isinstance(result, dict):
                return result

            self.submission.alarm_arns = result
            alarm_count = len(result)
            self.ui.display_info(f"✅ Loaded {alarm_count} alarm ARN(s)")

            # Extract unique regions from ARNs and store them
            regions = set()
            for arn in result:
                try:
                    resource_arn = build_resource_arn_object(arn)
                    if resource_arn.region and resource_arn.region != "global":
                        regions.add(resource_arn.region)
                except Exception as e:
                    self.ui.display_warning(f"Failed to parse ARN {arn}: {e}")

            if regions and self.submission.workload_onboard:
                self.submission.workload_onboard.regions = sorted(list(regions))
                self.ui.display_info(
                    f"📍 Detected regions: {', '.join(sorted(regions))}"
                )

        return {}

    @session_step("Select Alarms", order=7)
    def _select_alarms(self) -> Dict[str, str]:
        """Select which alarms to ingest from discovered alarms."""
        if not hasattr(self.submission, "alarm_arns") or not self.submission.alarm_arns:
            self.ui.display_warning("No alarms available for selection.")
            return {ACTION_KEY: ACTION_BACK}

        result = select_cloudwatch_alarms(
            ui=self.ui, alarm_arns=self.submission.alarm_arns
        )

        if isinstance(result, dict):
            return result

        self.submission.alarm_arns = result

        # Confirm before proceeding to validation
        self.ui.display_info(
            "\nℹ️  Next, we'll validate these alarms for noise patterns and suitability. "
            "Validation results will be noted in your ingestion request."
        )
        proceed = self.ui.prompt_confirm("Proceed to validation?", default=True)

        if not proceed:
            return {ACTION_KEY: ACTION_BACK}

        return {}

    @session_step("Validate Alarms", order=8)
    def _validate_alarms(self) -> Dict[str, str]:
        """Validate alarms for ingestion."""

        if not hasattr(self.submission, "alarm_arns") or not self.submission.alarm_arns:
            self.ui.display_warning("No alarms available for validation.")
            return {ACTION_KEY: ACTION_BACK}

        alarm_count = len(self.submission.alarm_arns)
        self.ui.display_info(f"🔍 Validating {alarm_count} alarm(s)...")

        try:
            validation_results = self.comprehensive_validator.validate_alarms(
                self.submission.alarm_arns
            )
        except Exception as e:
            self.ui.display_warning(f"⚠️  Validation error: {str(e)}")
            validation_results = []

        # Convert to AlarmValidation objects for cache
        alarm_validations = []

        for result in validation_results:
            alarm_validation = AlarmValidation(
                alarm_arn=result.alarm_arn,
                onboarding_status=result.onboarding_status,
                is_noisy=result.is_noisy,
                remarks_for_customer=result.remarks_for_customer,
                remarks_for_idr=result.remarks_for_idr,
            )
            alarm_validations.append(alarm_validation)

        self.submission.alarm_validation = alarm_validations

        # Create AlarmCreation objects
        alarm_creations = []
        for alarm_arn in self.submission.alarm_arns:
            alarm_name = alarm_arn.split(":")[-1] if ":" in alarm_arn else alarm_arn

            alarm_creation = AlarmCreation(
                alarm_arn=alarm_arn,
                is_selected=True,
                already_exists=True,
                resource_arn=None,
                alarm_configuration=AlarmConfiguration(alarm_name=alarm_name),
            )
            alarm_creations.append(alarm_creation)

        self.submission.alarm_creation = alarm_creations

        self.ui.display_info("✅ Validation complete")
        return {}

    @session_step("Confirm Ingestion", order=9)
    def _confirm_ingestion(self) -> Dict[str, str]:
        """Present confirmation summary and get approval for alarm ingestion."""
        if not hasattr(self.submission, "alarm_arns") or not self.submission.alarm_arns:
            self.ui.display_warning("No alarms available for ingestion.")
            return {ACTION_KEY: ACTION_BACK}

        alarm_count = len(self.submission.alarm_arns)
        self.ui.display_info(
            f"📋 Ready to ingest {alarm_count} CloudWatch alarm(s) into IDR"
        )

        if (
            hasattr(self.submission, "alarm_contacts")
            and self.submission.alarm_contacts
        ):
            display_alarm_contact_summary(ui=self.ui, submission=self.submission)

        proceed = self.ui.prompt_confirm(
            f"Proceed with ingesting these {alarm_count} alarm(s) into IDR?",
            default=True,
        )

        if not proceed:
            self.ui.display_info("Returning to input method selection...")
            # Clear alarm data to start fresh
            self.submission.alarm_arns = []
            self.submission.alarm_creation = []
            if hasattr(self.submission, "input_method"):
                delattr(self.submission, "input_method")
            # Set to step 6 so ACTION_BACK decrements to step 5 (Select Input Method)
            self.current_step = 5
            self._save_progress()
            return {ACTION_KEY: ACTION_BACK}

        # Update alarm_ingestion with chosen alarms
        if not self.submission.alarm_ingestion:
            self.submission.alarm_ingestion = AlarmIngestion(
                onboarding_alarms=[],
                contacts_approval_timestamp=datetime.now(timezone.utc),
            )

        # Convert alarm_creation entries to onboarding alarms
        if self.submission.alarm_creation:
            self.submission.alarm_ingestion.onboarding_alarms.extend(
                self.alarm_service.convert_created_alarms_to_onboarding_alarms(
                    self.submission.alarm_creation, self.submission.alarm_contacts
                )
            )
        self.submission.alarm_ingestion.contacts_approval_timestamp = datetime.now(
            timezone.utc
        )

        self.ui.display_info("✅ Alarms successfully submitted for IDR onboarding!")
        return {}

    @session_step("Working on the Support Case", order=10)
    def handle_support_case(self) -> Dict[str, Any]:
        """Create or update support case for alarm ingestion."""
        from aws_idr_customer_cli.exceptions import (
            AlarmCreationValidationError,
            AlarmIngestionValidationError,
            SupportCaseAlreadyExistsError,
        )

        case_id = self._get_existing_support_case_id()
        if case_id:
            try:
                self.support_case_service.update_case_with_attachment_set(
                    session_id=self.session_id, case_id=case_id
                )
                self.ui.display_info("✅ Support case has been updated")
                self._display_support_case(case_id)
            except (AlarmCreationValidationError, AlarmIngestionValidationError) as e:
                self.ui.display_info(str(e))
                return {}
        else:
            try:
                case_id = self.support_case_service.create_case(self.session_id)
                self.submission.workload_onboard.support_case_id = case_id
                self.ui.display_info("✅ Support case has been created")
                self._display_support_case(case_id)
            except SupportCaseAlreadyExistsError as e:
                self.ui.display_info(str(e))
                return {}

        return {}

    @session_step("Check Service Linked Role", order=11)
    def _check_service_linked_role(self) -> Dict[str, Any]:
        """Check if Service Linked Role exists and prompt to create if needed."""
        result: Dict[str, Any] = check_and_create_service_linked_role(
            self.ui, self._iam_manager
        )
        return result

    def _get_existing_support_case_id(self) -> Optional[str]:
        """Get existing support case ID from submission."""
        if (
            self.submission
            and self.submission.workload_onboard
            and self.submission.workload_onboard.support_case_id
        ):
            case_id: Optional[str] = self.submission.workload_onboard.support_case_id
            return case_id
        return None

    def _display_support_case(self, case_id: str) -> None:
        """Display support case information."""
        self.ui.display_info(f"📋 Support Case ID: {case_id}")
        case_url = (
            "https://support.console.aws.amazon.com/support/home"
            f"#/case/?displayId={case_id}"
        )
        self.ui.display_info(f"🔗 View case: {case_url}")
