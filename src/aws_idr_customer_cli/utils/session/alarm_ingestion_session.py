from datetime import datetime, timezone
from typing import Any, Dict, Optional, cast

from arnparse import arnparse
from retry import retry

from aws_idr_customer_cli.data_accessors.eventbridge_accessor import (
    EventBridgeAccessor,
)
from aws_idr_customer_cli.exceptions import ValidationError
from aws_idr_customer_cli.services.create_alarm.alarm_service import AlarmService
from aws_idr_customer_cli.services.file_cache.data import (
    AlarmConfiguration,
    AlarmCreation,
    AlarmIngestion,
    AlarmValidation,
    ApmIngestion,
)
from aws_idr_customer_cli.utils.alarm_contact_collection import (
    collect_alarm_contact_info,
    display_alarm_contact_summary,
    offer_alarm_contact_correction_workflow,
)
from aws_idr_customer_cli.utils.apm.apm_constants import (
    APM_ALERT_IDENTIFIER_REQUIRED_ERROR,
    EVENTBRIDGE_MAX_RETRIES_ERROR,
    EVENTBRIDGE_NAME_VALIDATION_ERROR,
    EVENTBRIDGE_NO_BUSES_ERROR,
    IDR_EVENTBRIDGE_NAME_PATTERN,
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
from aws_idr_customer_cli.utils.support_case_utils import (
    handle_duplicate_support_case_interactive,
)
from aws_idr_customer_cli.utils.validate_alarm.alarm_validator import AlarmValidator
from aws_idr_customer_cli.utils.validation.apm_validation import (
    validate_aws_region,
)
from aws_idr_customer_cli.utils.workload_meta_data_collection_utils import (
    collect_regions,
)
from aws_idr_customer_cli.utils.workload_meta_data_collection_utils import (
    collect_workload_info as utils_collect_workload_info,
)
from aws_idr_customer_cli.utils.workload_meta_data_collection_utils import (
    review_and_update_workload as utils_review_and_update_workload,
)

APM_VALIDATION_MAX_RETRIES = 2


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
        eventbridge_accessor: EventBridgeAccessor,
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
        self.eventbridge_accessor = eventbridge_accessor
        self._is_apm_flow = False
        self._has_eligible_buses = True

        # Restore workflow type on resume (submission is set by parent __init__)
        if resume_session_id and hasattr(self, "submission") and self.submission:
            if self.submission.apm_ingestion:
                self._is_apm_flow = True
            elif (
                self.submission.alarm_ingestion
                and self.submission.alarm_ingestion.workflow_type
            ):
                self._is_apm_flow = (
                    self.submission.alarm_ingestion.workflow_type == "apm"
                )

    def _display_resume_info(self) -> None:
        """Restore workflow type when resuming session."""
        if self.submission:
            if self.submission.apm_ingestion:
                self._is_apm_flow = True
            elif (
                self.submission.alarm_ingestion
                and self.submission.alarm_ingestion.workflow_type
            ):
                self._is_apm_flow = (
                    self.submission.alarm_ingestion.workflow_type == "apm"
                )

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

    @session_step("Select Alarm Type", order=5)
    def _select_alarm_type(self) -> Dict[str, str]:
        """Select between CloudWatch alarms or APM alarms."""
        self.ui.display_info("🔍 Alarm Ingestion")
        self.ui.display_info("What would you like to ingest?")

        options = [
            "CloudWatch Alarms",
            "APM Alarms (eg. Datadog, New Relic etc.)",
        ]

        choice = self.ui.select_option(options, "Select alarm type")

        if choice == 0:
            self._is_apm_flow = False
            if not self.submission.alarm_ingestion:
                self.submission.alarm_ingestion = AlarmIngestion(
                    onboarding_alarms=[],
                    contacts_approval_timestamp=datetime.now(timezone.utc),
                    workflow_type="cloudwatch",
                )
            else:
                self.submission.alarm_ingestion.workflow_type = "cloudwatch"
        elif choice == 1:
            self._is_apm_flow = True
            if not self.submission.alarm_ingestion:
                self.submission.alarm_ingestion = AlarmIngestion(
                    onboarding_alarms=[],
                    contacts_approval_timestamp=datetime.now(timezone.utc),
                    workflow_type="apm",
                )
            else:
                self.submission.alarm_ingestion.workflow_type = "apm"
        else:
            return {ACTION_KEY: ACTION_BACK}

        return {}

    @session_step("Configure Alarm Ingestion", order=6)
    def _select_input_method_or_configure_apm(self) -> Dict[str, str]:
        """Select input method for ingesting CW alarms or APM identifiers."""
        if self._is_apm_flow:
            return self._configure_custom_eventbus()
        else:
            return self._select_cloudwatch_input_method()

    def _select_cloudwatch_input_method(self) -> Dict[str, str]:
        """Select how to provide CloudWatch alarm ARNs."""
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

    def _configure_custom_eventbus(self) -> Dict[str, str]:
        """Configure Custom EventBridge event bus ARN for APM."""

        # Provide context about what we're looking for
        self.ui.display_info("📡 APM EventBridge Configuration")
        self.ui.display_info(
            "To ingest APM alarms, we need the EventBridge CustomEventBus "
            "that was created as part of your APM CloudFormation stack."
        )

        # Collect single region for discovering custom event bus and for workload info
        self.ui.display_info(
            "📍 Enter the region where your CustomEventBus is deployed"
        )
        regions = collect_regions(self.ui, single_region=True)
        if not regions:
            regions = [DEFAULT_REGION]
        if self.submission.workload_onboard:
            self.submission.workload_onboard.regions = regions

        # Get and display eligible event buses
        eligible_buses = self._get_eligible_event_buses()
        if not eligible_buses:
            self.ui.display_error(EVENTBRIDGE_NO_BUSES_ERROR)
            if self.submission.workload_onboard:
                self.submission.workload_onboard.regions = []
            return {ACTION_KEY: ACTION_BACK}

        self._display_eligible_event_buses(eligible_buses)

        # Check if only one event bus found
        if len(eligible_buses) == 1:
            event_bus_arn = eligible_buses[0][1].get("Arn", "")
            if self.ui.prompt_confirm(
                f"Use this event bus: {event_bus_arn}?", default=True
            ):
                self._save_apm_ingestion(event_bus_arn)
                self.ui.display_info("✅ Event bus configured successfully")
                return {}

        # Multiple buses or user declined single bus - prompt for ARN
        try:
            event_bus_arn = self._prompt_and_validate_event_bus_arn()
            self._save_apm_ingestion(event_bus_arn)
            self.ui.display_info("✅ Event bus validated successfully")
            return {}
        except ValidationError:
            self.ui.display_error(EVENTBRIDGE_MAX_RETRIES_ERROR)
            self.current_step = 5
            self._save_progress()
            return {ACTION_KEY: ACTION_BACK}

    @retry(exceptions=ValidationError, tries=APM_VALIDATION_MAX_RETRIES)
    def _prompt_and_validate_event_bus_arn(self) -> str:
        """Prompt for and validate EventBridge ARN with retry."""
        event_bus_arn = self._prompt_for_event_bus_arn()
        if not event_bus_arn:
            self.ui.display_warning("EventBridge ARN cannot be empty")
            raise ValidationError("Empty input")

        validation_result = self._validate_event_bus_arn(event_bus_arn)
        if not validation_result["valid"]:
            self.ui.display_warning(validation_result["error"])
            raise ValidationError(validation_result["error"])

        return event_bus_arn

    def _get_eligible_event_buses(self) -> list:
        """Get eligible event buses containing IDR pattern across all regions.

        Returns:
            List of tuples (region, bus_dict)
        """
        if (
            not self.submission.workload_onboard
            or not self.submission.workload_onboard.regions
        ):
            return []

        all_eligible_buses = []
        for region in self.submission.workload_onboard.regions:
            try:
                response = self.eventbridge_accessor.list_event_buses(region)
                event_buses = response.get("EventBuses", [])

                eligible_buses = [
                    (region, bus)
                    for bus in event_buses
                    if IDR_EVENTBRIDGE_NAME_PATTERN in bus.get("Name", "")
                ]
                all_eligible_buses.extend(eligible_buses)
            except Exception as e:
                self.ui.display_warning(
                    f"⚠️  Failed to list event buses in {region}: {str(e)}"
                )
                continue

        return all_eligible_buses

    def _display_eligible_event_buses(self, eligible_buses: list) -> None:
        """Display eligible event buses.

        Args:
            eligible_buses: List of tuples (region, bus_dict)
        """
        self.ui.display_info("💡 Found eligible EventBridge event buses:")
        for region, bus in eligible_buses:
            bus_arn = bus.get("Arn", "")
            creation_time = bus.get("CreationTime")
            if creation_time:
                time_str = f" (created: {creation_time.strftime('%Y-%m-%d')})"
            else:
                time_str = ""
            self.ui.display_info(f"  • {bus_arn}{time_str}")

    def _prompt_for_event_bus_arn(self) -> str:
        """Prompt user for EventBridge event bus ARN."""
        return str(self.ui.prompt_input("Enter EventBridge event bus ARN")).strip()

    def _save_apm_ingestion(self, event_bus_arn: str) -> None:
        """Save APM ingestion configuration with EventBridge ARN."""
        from aws_idr_customer_cli.services.file_cache.data import ApmEventSource

        if not self.submission.apm_ingestion:
            self.submission.apm_ingestion = ApmIngestion(
                third_party_apm_identifier_list=[
                    ApmEventSource(
                        event_bridge_arn=event_bus_arn,
                        third_party_apm_identifiers=[],
                        eventbus_validation_status="VALIDATED",
                    )
                ]
            )
        else:
            # Update first EventBridge ARN or add new one
            if self.submission.apm_ingestion.third_party_apm_identifier_list:
                self.submission.apm_ingestion.third_party_apm_identifier_list[
                    0
                ].event_bridge_arn = event_bus_arn
            else:
                self.submission.apm_ingestion.third_party_apm_identifier_list.append(
                    ApmEventSource(
                        event_bridge_arn=event_bus_arn,
                        third_party_apm_identifiers=[],
                        eventbus_validation_status="VALIDATED",
                    )
                )

    def _validate_event_bus_arn(self, arn: str) -> Dict[str, Any]:
        """Validate EventBridge event bus ARN format and existence."""
        try:
            parsed = arnparse(arn)
        except Exception:
            return {
                "valid": False,
                "error": (
                    f"Invalid EventBridge ARN format: {arn}. "
                    "Expected format: arn:aws:events:region:account:event-bus/bus-name"
                ),
            }

        if parsed.service != "events":
            return {
                "valid": False,
                "error": f"Invalid service. Expected 'events', got '{parsed.service}'",
            }

        resource_type = parsed.resource_type
        if resource_type != "event-bus":
            return {
                "valid": False,
                "error": f"ARN must be for an event bus, got '{resource_type}'",
            }

        # Validate EventBridge name contains IDR pattern
        if IDR_EVENTBRIDGE_NAME_PATTERN not in parsed.resource:
            return {
                "valid": False,
                "error": EVENTBRIDGE_NAME_VALIDATION_ERROR.format(
                    resource=parsed.resource
                ),
            }

        try:
            region = parsed.region
            validate_aws_region(region, self.validator)
            self.eventbridge_accessor.describe_event_bus(region, name=arn)
            return {"valid": True}
        except ValueError as e:
            return {"valid": False, "error": f"Event bus not found: {str(e)}"}
        except Exception as e:
            return {"valid": False, "error": f"Failed to validate event bus: {str(e)}"}

    @session_step("Collect Alarms", order=7)
    def _discover_alarms_or_configure_identifiers(self) -> Dict[str, str]:
        """Discover CW alarms or configure APM alert identifiers."""
        if self._is_apm_flow:
            return self._configure_apm_identifiers()
        else:
            return self._discover_cloudwatch_alarms()

    def _configure_apm_identifiers(self) -> Dict[str, str]:
        """Configure APM alert identifiers with validation."""
        self.ui.display_info("🏷️  APM Alert Identifiers")
        self.ui.display_info(
            "Provide comma-separated alert identifiers that your APM sends "
            "(e.g., 'error-counts,cpu-utilization,latency')."
        )

        try:
            identifiers = self._prompt_and_validate_apm_identifiers()
            if (
                self.submission.apm_ingestion
                and self.submission.apm_ingestion.third_party_apm_identifier_list
            ):
                self.submission.apm_ingestion.third_party_apm_identifier_list[
                    0
                ].third_party_apm_identifiers = identifiers
            self.ui.display_info(
                f"✅ Configured {len(identifiers)} alert identifier(s)"
            )
            return {}
        except ValidationError:
            self.ui.display_error("Maximum validation attempts reached.")
            self.current_step = 5
            self._save_progress()
            return {ACTION_KEY: ACTION_BACK}

    @retry(exceptions=ValidationError, tries=APM_VALIDATION_MAX_RETRIES)
    def _prompt_and_validate_apm_identifiers(self) -> list:
        """Prompt for and validate APM identifiers with retry."""
        identifiers_input = self.ui.prompt_input(
            "Enter alert identifiers (comma-separated)"
        ).strip()

        identifiers = [i.strip() for i in identifiers_input.split(",") if i.strip()]

        if not identifiers:
            self.ui.display_warning(APM_ALERT_IDENTIFIER_REQUIRED_ERROR)
            raise ValidationError("Empty identifiers")

        return identifiers

    def _discover_cloudwatch_alarms(self) -> Dict[str, str]:
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

    @session_step("Confirm Configuration", order=8)
    def _confirm_configuration(self) -> Dict[str, str]:
        """Confirm alarm configuration (APM: event bus + identifiers, CloudWatch: select alarms)."""
        if self._is_apm_flow:
            return self._confirm_apm_configuration()
        else:
            return self._select_and_confirm_cloudwatch_alarms()

    @session_step("Validate Alarms", order=9)
    def _validate_alarms_step(self) -> Dict[str, str]:
        """Validate alarms (APM: skip, CloudWatch: validate)."""
        if self._is_apm_flow:
            self.ui.display_info("⏭️  Skipping identifier validation for APM alerts")
            return {}
        return self._validate_cloudwatch_alarms()

    @session_step("Confirm Alarm Ingestion", order=10)
    def _confirm_ingestion_step(self) -> Dict[str, str]:
        """Confirm alarm ingestion (shared for both APM and CloudWatch)."""
        if self._is_apm_flow:
            return self._confirm_apm_ingestion()
        else:
            return self._confirm_cloudwatch_ingestion()

    def _confirm_apm_configuration(self) -> Dict[str, str]:
        """Confirm APM configuration (event bus and identifiers)."""
        self.ui.display_info("📋 APM Configuration Summary")

        if (
            self.submission.apm_ingestion
            and self.submission.apm_ingestion.third_party_apm_identifier_list
        ):
            for (
                eb_source
            ) in self.submission.apm_ingestion.third_party_apm_identifier_list:
                self.ui.display_info(f"Event Bus: {eb_source.event_bridge_arn}")
                if eb_source.third_party_apm_identifiers:
                    identifiers = ", ".join(eb_source.third_party_apm_identifiers)
                    self.ui.display_info(f"Alert Identifiers: {identifiers}")

        proceed = self.ui.prompt_confirm(
            "Proceed with this configuration?", default=True
        )

        if not proceed:
            self.ui.display_info("Returning to EventBridge configuration...")
            self._is_apm_flow = True
            self.submission.apm_ingestion = None
            self.current_step = 6
            self._save_progress()
            return {ACTION_KEY: ACTION_BACK}

        return {}

    def _confirm_apm_ingestion(self) -> Dict[str, str]:
        """Final confirmation for APM alarm ingestion."""
        self.ui.display_info("📋 APM Alarm Ingestion Summary")
        self.ui.display_info("")

        if (
            self.submission.apm_ingestion
            and self.submission.apm_ingestion.third_party_apm_identifier_list
        ):
            for (
                eb_source
            ) in self.submission.apm_ingestion.third_party_apm_identifier_list:
                self.ui.display_info(f"Event Bus: {eb_source.event_bridge_arn}")
                if eb_source.third_party_apm_identifiers:
                    identifiers = ", ".join(eb_source.third_party_apm_identifiers)
                    self.ui.display_info(f"Alert Identifiers: {identifiers}")

        if self.submission.alarm_contacts:
            display_alarm_contact_summary(ui=self.ui, submission=self.submission)

        proceed = self.ui.prompt_confirm(
            "Proceed with ingesting APM alarms into IDR?", default=True
        )

        if not proceed:
            self.ui.display_info("Returning to EventBridge configuration...")
            self._is_apm_flow = True
            self.submission.apm_ingestion = None
            self.current_step = 5
            self._save_progress()
            return {ACTION_KEY: ACTION_BACK}

        self.ui.display_info("✅ Alarms successfully submitted for IDR onboarding!")
        return {}

    def _select_and_confirm_cloudwatch_alarms(self) -> Dict[str, str]:
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

    def _validate_cloudwatch_alarms(self) -> Dict[str, str]:
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

    def _confirm_cloudwatch_ingestion(self) -> Dict[str, str]:
        """Final confirmation for CloudWatch alarm ingestion."""
        if not hasattr(self.submission, "alarm_arns") or not self.submission.alarm_arns:
            self.ui.display_warning("No alarms available for ingestion.")
            return {ACTION_KEY: ACTION_BACK}

        alarm_count = len(self.submission.alarm_arns)
        self.ui.display_info("📋 CloudWatch Alarm Ingestion Summary")
        self.ui.display_info("")
        self.ui.display_info(f"Total Alarms: {alarm_count}")

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
            self.ui.display_info("Returning to alarm type selection...")
            # Clear alarm data to start fresh
            self.submission.alarm_arns = []
            self.submission.alarm_creation = []
            if hasattr(self.submission, "input_method"):
                delattr(self.submission, "input_method")
            self._is_apm_flow = False
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

    @session_step("Working on the Support Case", order=11)
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
