import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from arnparse import arnparse
from injector import inject

from aws_idr_customer_cli.clients.iam import BotoIamManager
from aws_idr_customer_cli.core.interactive.ui import InteractiveUI
from aws_idr_customer_cli.data_accessors.eventbridge_accessor import EventBridgeAccessor
from aws_idr_customer_cli.exceptions import SupportCaseAlreadyExistsError
from aws_idr_customer_cli.input.input_resource_discovery import InputResourceDiscovery
from aws_idr_customer_cli.models.non_interactive_config import (
    AlarmContactsConfig,
    AlarmIngestionConfig,
    OutputFormat,
)
from aws_idr_customer_cli.services.create_alarm.alarm_service import AlarmService
from aws_idr_customer_cli.services.file_cache.data import (
    AlarmContacts,
    AlarmIngestion,
    AlarmValidation,
    ApmEventSource,
    ApmIngestion,
    ContactInfo,
    OnboardingAlarm,
    OnboardingStatus,
    OnboardingSubmission,
    ProgressTracker,
    WorkloadOnboard,
)
from aws_idr_customer_cli.services.file_cache.file_cache_service import FileCacheService
from aws_idr_customer_cli.services.input_module.resource_finder_service import (
    ResourceFinderService,
)
from aws_idr_customer_cli.services.non_interactive_base_service import (
    NonInteractiveServiceBase,
)
from aws_idr_customer_cli.services.support_case_service import SupportCaseService
from aws_idr_customer_cli.utils.alarm_contact_collection import (
    display_alarm_contact_summary,
)
from aws_idr_customer_cli.utils.arn_utils import extract_account_id_from_arn
from aws_idr_customer_cli.utils.constants import CLI_VERSION, SCHEMA_VERSION
from aws_idr_customer_cli.utils.execution_mode import (
    ExecutionMode,
)
from aws_idr_customer_cli.utils.log_handlers import CliLogger
from aws_idr_customer_cli.utils.service_linked_role_utils import (
    SLR_ROLE_NAME,
    SLR_SERVICE_NAME,
)
from aws_idr_customer_cli.utils.session.session_store import SessionStore
from aws_idr_customer_cli.utils.support_case_utils import extract_case_id_from_error
from aws_idr_customer_cli.utils.validate_alarm.alarm_validator import (
    AlarmValidator,
)
from aws_idr_customer_cli.utils.validate_alarm.alarm_validator import (
    OnboardingStatus as ValidationStatus,
)
from aws_idr_customer_cli.utils.validation.validator import Validate


class NonInteractiveAlarmIngestionService(NonInteractiveServiceBase):
    """Service for non-interactive alarm ingestion."""

    @inject
    def __init__(
        self,
        ui: InteractiveUI,
        store: SessionStore,
        input_resource_discovery: InputResourceDiscovery,
        validator: Validate,
        support_case_service: SupportCaseService,
        file_cache_service: FileCacheService,
        alarm_validator: AlarmValidator,
        alarm_service: AlarmService,
        iam_manager: BotoIamManager,
        resource_finder_service: ResourceFinderService,
        logger: CliLogger,
        eventbridge_accessor: EventBridgeAccessor,
    ) -> None:
        super().__init__(
            ui=ui,
            store=store,
            input_resource_discovery=input_resource_discovery,
            validator=validator,
            support_case_service=support_case_service,
            file_cache_service=file_cache_service,
        )
        self._alarm_validator = alarm_validator
        self._alarm_service = alarm_service
        self._iam_manager = iam_manager
        self._resource_finder_service = resource_finder_service
        self._eventbridge_accessor = eventbridge_accessor
        self.logger = logger

    def _display_dry_run_specific_info(self) -> None:
        """Display dry run info specific to alarm ingestion."""
        self.ui.display_info(
            "Alarm ingestion, support case creation, and service-linked role "
            "creation will be skipped",
            style="yellow",
        )

    @staticmethod
    def _create_alarm_contact_data(
        contacts_config: AlarmContactsConfig,
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

        return AlarmContacts(
            primary_contact=primary_contact, escalation_contact=escalation_contact
        )

    def ingest_alarms_from_config(
        self, config: Dict[str, Any], account_id: str
    ) -> None:
        """Execute complete alarm ingestion from config data."""
        config_obj = AlarmIngestionConfig.from_dict(config)
        json_output: Dict[str, Any] = {}
        is_json_mode = config_obj.options.output_format == OutputFormat.JSON
        try:
            submission = self.execute_from_config(config=config, account_id=account_id)
            if is_json_mode:
                json_output["status"] = "success"
                json_output["data"] = self._create_filtered_json_output(
                    submission=submission
                )
        except Exception as e:
            if is_json_mode:
                json_output["status"] = "failed"
                json_output["error"] = str(e)
            else:
                raise e
        finally:
            if is_json_mode:  # to handle outputting json only for json
                with self.ui.unsilenced_output():
                    self.ui.display_info(
                        json.dumps(json_output, indent=2, ensure_ascii=False)
                    )

    def execute_from_config(
        self, config: Dict[str, Any], account_id: str
    ) -> OnboardingSubmission:
        """Execute alarm ingestion from config data."""
        config_obj = AlarmIngestionConfig.from_dict(config)
        self.set_output_format(output_format=config_obj.options.output_format)
        dry_run_mode = config_obj.options.dry_run

        if dry_run_mode:
            self._display_dry_run_header()

        self._validate_mixed_config(config_obj)

        self.validate_config(
            workload_name=config_obj.workload.name,
            workload_regions=config_obj.workload.regions,
            alarm_contacts_config=config_obj.contacts,
            discovery_config=config_obj.discovery,
        )

        # Setup initial data
        workload, alarm_contacts, temp_submission = self._setup_initial_data(
            config_obj=config_obj, account_id=account_id
        )
        display_alarm_contact_summary(ui=self.ui, submission=temp_submission)

        alarm_arns = []
        if config_obj.discovery:
            alarm_arns = self._discover_and_display_alarms(config_obj=config_obj)

        apm_data = None
        if config_obj.third_party_apm:
            apm_data = self._process_apm_alerts(
                config_obj.third_party_apm, account_id, dry_run_mode
            )

        # Create submission
        submission = self._create_submission_with_alarms(
            workload=workload,
            account_id=account_id,
            alarm_contacts=alarm_contacts,
            alarm_arns=alarm_arns,
            apm_data=apm_data,
        )

        submission.execution_mode = ExecutionMode.NON_INTERACTIVE

        session_id = self.store.create(submission=submission)
        self.ui.display_info(f"📝 Created session: {session_id}")

        # Validate and process alarms
        alarm_validations = self._validate_and_process_alarms(
            alarm_arns=alarm_arns, submission=submission, dry_run_mode=dry_run_mode
        )

        # Create alarm ingestion data
        if not dry_run_mode and alarm_validations:
            self._populate_alarm_ingestion_data(
                submission=submission,
                alarm_validations=alarm_validations,
                alarm_contacts=alarm_contacts,
            )
        elif apm_data and not submission.alarm_ingestion:
            # For APM-only configurations, create empty alarm ingestion with timestamp
            submission.alarm_ingestion = AlarmIngestion(
                onboarding_alarms=[],
                contacts_approval_timestamp=datetime.now(timezone.utc),
            )
        self.store.update(session_id=session_id, submission=submission)

        # Handle support case and SLR
        case_id, slr_created = self._handle_post_validation_tasks(
            submission=submission,
            session_id=session_id,
            config_obj=config_obj,
            dry_run_mode=dry_run_mode,
        )

        self.store.update(session_id=session_id, submission=submission)
        self._display_final_summary(
            submission=submission,
            case_id=case_id,
            slr_created=slr_created,
            alarm_count=len(alarm_arns),
            apm_data=apm_data,
        )

        return submission

    def _setup_initial_data(
        self, config_obj: AlarmIngestionConfig, account_id: str
    ) -> tuple:
        """Setup initial workload and contact data."""
        workload = self._create_workload_data(
            name=config_obj.workload.name, regions=config_obj.workload.regions
        )
        alarm_contacts = self._create_alarm_contact_data(
            contacts_config=config_obj.contacts
        )
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
        return workload, alarm_contacts, temp_submission

    def _discover_and_display_alarms(
        self, config_obj: AlarmIngestionConfig
    ) -> List[str]:
        """Discover alarms and display progress."""
        if config_obj.discovery.method.value == "arns":
            self.ui.display_info(
                f"\n🔍 Loading {len(config_obj.discovery.arns)} alarm(s) from ARNs..."
            )
        else:
            self.ui.display_info("\n🔍 Discovering alarms by tags...")

        alarm_arns = self._discover_alarms(
            discovery_config=config_obj.discovery, regions=config_obj.workload.regions
        )
        self.ui.display_info(f"✅ Discovered {len(alarm_arns)} alarm(s)", style="green")
        return alarm_arns

    def _create_submission_with_alarms(
        self,
        workload: WorkloadOnboard,
        account_id: str,
        alarm_contacts: AlarmContacts,
        alarm_arns: List[str],
        apm_data: Optional[ApmIngestion] = None,
    ) -> OnboardingSubmission:
        """Create submission with alarm data."""
        submission = self._create_submission(
            workload=workload,
            resources=[],
            account_id=account_id,
            progress_tracker=self._create_ingestion_progress_tracker(),
            alarm_contacts=alarm_contacts,
        )
        submission.alarm_arns = alarm_arns
        submission.progress.alarm_ingestion = self._create_ingestion_progress_tracker()

        if apm_data:
            submission.apm_ingestion = apm_data

        return submission

    def _validate_and_process_alarms(
        self,
        alarm_arns: List[str],
        submission: OnboardingSubmission,
        dry_run_mode: bool,
    ) -> List[AlarmValidation]:
        """Validate alarms and return validation results."""
        if not alarm_arns:
            return []

        if dry_run_mode:
            self.ui.display_info(
                "⏭️  Skipping validation (dry-run mode)", style="yellow"
            )
            return []

        try:
            self._alarm_validator.ui.set_silent_mode(True)
            validation_results_list = self._alarm_validator.validate_alarms(
                alarm_arns=alarm_arns
            )
            alarm_validations = []
            validation_counts = {"valid": 0, "invalid": 0, "warnings": 0}

            for result in validation_results_list:
                alarm_validation = AlarmValidation(
                    alarm_arn=result.alarm_arn,
                    onboarding_status=result.onboarding_status,
                    is_noisy=result.is_noisy,
                    remarks_for_customer=result.remarks_for_customer,
                    remarks_for_idr=result.remarks_for_idr,
                    noise_analysis={},
                )
                alarm_validations.append(alarm_validation)

                if result.status == ValidationStatus.YES:
                    validation_counts["valid"] += 1
                elif result.status == ValidationStatus.NO:
                    validation_counts["invalid"] += 1
                else:
                    validation_counts["warnings"] += 1

            submission.alarm_validation = alarm_validations
            self.ui.display_info(
                f"✅ Validation: {validation_counts['valid']} valid, "
                f"{validation_counts['invalid']} invalid, "
                f"{validation_counts['warnings']} warnings",
                style="green",
            )
            return alarm_validations
        except Exception as e:
            self.ui.display_warning(f"Validation failed: {type(e).__name__}: {str(e)}")
            import traceback

            self.ui.display_warning(traceback.format_exc())
            raise
        finally:
            self._alarm_validator.ui.set_silent_mode(False)

    @staticmethod
    def _populate_alarm_ingestion_data(
        submission: OnboardingSubmission,
        alarm_validations: List[AlarmValidation],
        alarm_contacts: AlarmContacts,
    ) -> None:
        """Populate alarm ingestion data in submission."""
        onboarding_alarms = [
            OnboardingAlarm(
                alarm_arn=val.alarm_arn,
                primary_contact=alarm_contacts.primary_contact,
                escalation_contact=alarm_contacts.escalation_contact,
            )
            for val in alarm_validations
        ]
        submission.alarm_ingestion = AlarmIngestion(
            onboarding_alarms=onboarding_alarms,
            contacts_approval_timestamp=datetime.now(timezone.utc),
        )

    def _handle_post_validation_tasks(
        self,
        submission: OnboardingSubmission,
        session_id: str,
        config_obj: AlarmIngestionConfig,
        dry_run_mode: bool,
    ) -> tuple:
        """Handle support case and service linked role creation."""
        case_id = None
        if config_obj.options.create_support_case:
            self.ui.display_info("\n📋 Creating/updating support case...")
            case_id = self._handle_support_case_with_duplicate_handling(
                submission=submission,
                session_id=session_id,
                config_obj=config_obj,
                dry_run_mode=dry_run_mode,
            )
        else:
            self.ui.display_info("⏭️  Skipping support case creation", style="yellow")

        slr_created = False
        if config_obj.options.create_service_linked_role:
            self.ui.display_info("\n🔧 Checking service linked role...")
            slr_created = self._handle_service_linked_role(dry_run_mode=dry_run_mode)
        else:
            self.ui.display_info(
                "⏭️  Skipping service-linked role creation", style="yellow"
            )

        return case_id, slr_created

    @staticmethod
    def _create_ingestion_progress_tracker() -> ProgressTracker:
        """Create progress tracker for alarm ingestion."""
        return ProgressTracker(
            current_step=6,
            total_steps=10,
            step_name="alarm_ingestion_completed",
            completed_steps=[
                "workload_info",
                "contacts",
                "discovery",
                "validation",
                "ingestion",
            ],
        )

    def _discover_alarms(self, discovery_config: Any, regions: List[str]) -> List[str]:
        """Discover alarms based on configuration."""
        if discovery_config.method.value == "tags":
            if not discovery_config.tags:
                raise ValueError("Tags required for tag-based discovery")

            # Build tag filters for non-interactive discovery
            tag_filters = [
                {"Key": k, "Values": [v]} for k, v in discovery_config.tags.items()
            ]

            # Use resource_finder_service directly to avoid interactive prompts
            resources = self._resource_finder_service.find_resources_by_tags(
                tags=tag_filters,
                regions=regions,
                resource_types=["cloudwatch:alarm"],
                resource_label="CloudWatch alarms",
            )

            if not resources:
                return []

            # Extract ARN strings
            alarm_arns: List[str] = [
                r["ResourceArn"].arn for r in resources if "ResourceArn" in r
            ]
            return alarm_arns
        elif discovery_config.method.value == "arns":
            if not discovery_config.arns:
                raise ValueError("ARNs required for ARN-based discovery")
            return list(discovery_config.arns)
        else:
            raise ValueError(f"Unsupported discovery method: {discovery_config.method}")

    def _handle_support_case_with_duplicate_handling(
        self,
        submission: OnboardingSubmission,
        session_id: str,
        config_obj: AlarmIngestionConfig,
        dry_run_mode: bool,
    ) -> Optional[str]:
        """Handle support case creation with duplicate detection."""
        if dry_run_mode:
            self.ui.display_info(
                "🔍 DRY RUN: Would create support case", style="yellow"
            )
            return None

        # Get existing case ID if any
        existing_case_id: Optional[str] = None
        if submission.workload_onboard and submission.workload_onboard.support_case_id:
            existing_case_id = submission.workload_onboard.support_case_id

        try:
            if existing_case_id:
                # Update existing case
                self._file_cache_service.file_cache = submission
                self._support_case_service.file_cache_service.file_cache = submission
                self._support_case_service.update_case_with_attachment_set(
                    session_id=session_id, case_id=existing_case_id
                )
                self.ui.display_info(
                    "✅ Support case updated successfully", style="green"
                )
                return existing_case_id
            else:
                # Create new case
                self._file_cache_service.file_cache = submission
                self._support_case_service.file_cache_service.file_cache = submission
                # create_case returns str
                new_case_id: str = self._support_case_service.create_case(
                    session_id=session_id
                )
                if submission.workload_onboard:
                    submission.workload_onboard.support_case_id = new_case_id
                self.ui.display_info(
                    f"✅ Support case created: {new_case_id}", style="green"
                )
                return new_case_id
        except SupportCaseAlreadyExistsError as e:
            if config_obj.options.update_existing_case:
                existing_case_id = extract_case_id_from_error(str(e))
                if existing_case_id:
                    self.ui.display_info(f"Updating existing case: {existing_case_id}")
                    self._support_case_service.update_case_with_attachment_set(
                        session_id=session_id, case_id=existing_case_id
                    )
                    if submission.workload_onboard:
                        submission.workload_onboard.support_case_id = existing_case_id
                    self.ui.display_info(
                        "✅ Support case updated successfully", style="green"
                    )
                    return existing_case_id
            return None
        except Exception as e:
            self.ui.display_warning(
                f"⚠️  Support case handling failed: {type(e).__name__}: {str(e)}"
            )
            import traceback

            if self._should_display_ui():
                self.ui.display_warning(traceback.format_exc())
            return None

    def _handle_service_linked_role(self, dry_run_mode: bool = False) -> bool:
        """Handle service linked role creation."""
        if dry_run_mode:
            self.ui.display_info(
                "🔍 DRY RUN: Would check and create service-linked role", style="yellow"
            )
            return True

        try:
            self.ui.display_info("Checking Service Linked Role for IDR")

            if self._iam_manager.service_linked_role_exists(role_name=SLR_ROLE_NAME):
                self.ui.display_info(
                    "✅ Service Linked Role already exists", style="green"
                )
                return False

            self.ui.display_info("Creating Service Linked Role for IDR")
            role_name = self._iam_manager.create_service_linked_role(
                service_name=SLR_SERVICE_NAME
            )
            self.ui.display_info(
                f"✅ Created Service Linked Role: {role_name}", style="green"
            )
            return True

        except Exception as e:
            self.ui.display_warning(f"Service Linked Role handling failed: {e}")
            return False

    def _display_final_summary(
        self,
        submission: OnboardingSubmission,
        case_id: Optional[str],
        slr_created: bool,
        alarm_count: int,
        apm_data: Optional[ApmIngestion] = None,
    ) -> None:
        """Display final summary of alarm ingestion."""
        self.ui.display_info("✅ Alarm ingestion completed successfully", style="green")

        summary_data = {
            "Workload name": (
                submission.workload_onboard.name
                if submission.workload_onboard
                else "Unknown"
            ),
            "CloudWatch alarms ingested": str(alarm_count),
            "Support case ID": case_id or "None",
            "Service linked role created": "Yes" if slr_created else "No",
        }

        if apm_data:
            # Count total identifiers across all EventBridge ARNs
            total_identifiers = sum(
                len(eb.third_party_apm_identifiers)
                for eb in apm_data.third_party_apm_identifier_list
            )
            summary_data["APM EventBridge ARNs"] = str(
                len(apm_data.third_party_apm_identifier_list)
            )
            summary_data["APM alerts ingested"] = str(total_identifiers)

        self.ui.display_result("📋 Alarm ingestion summary", summary_data)

    def _create_filtered_json_output(
        self, submission: OnboardingSubmission
    ) -> Dict[str, Any]:
        """Create filtered JSON output for alarm ingestion, keeping validation data."""
        json_data = submission.to_dict()

        # Remove unnecessary fields but KEEP alarm_validation for ingestion
        unnecessary_fields = [
            "filehash",
            "progress",
            "progress_tracker",
            "workload_to_alarm_handoff",
            "resource_discovery_methods",
            "resource_tags",
        ]

        for field in unnecessary_fields:
            json_data.pop(field, None)

        return dict(json_data)

    def _validate_mixed_config(self, config_obj: AlarmIngestionConfig) -> None:
        """Validate mixed configuration requirements."""
        has_cloudwatch = config_obj.discovery is not None
        has_apm = config_obj.third_party_apm is not None

        if not (has_cloudwatch or has_apm):
            raise ValueError(
                "At least one of 'discovery' or 'third_party_apm' must be provided"
            )

    def _process_apm_alerts(
        self, apm_config: Any, account_id: str, dry_run_mode: bool
    ) -> Optional[ApmIngestion]:
        """Process APM alert configuration for multiple EventBridge ARNs."""
        self.ui.display_info("\n🔍 Validating APM configuration...")

        apm_ingestion_list = []
        validation_failures = []

        for idx, eb_config in enumerate(apm_config.third_party_apm_identifier_list, 1):
            self.ui.display_info(
                f"  Processing EventBridge {idx}/{len(apm_config.third_party_apm_identifier_list)}"
                f": {eb_config.eventbridge_arn}"
            )

            try:
                if dry_run_mode:
                    self.ui.display_info(
                        "    ⏭️  Skipping validation (dry-run mode)", style="yellow"
                    )
                    apm_ingestion_list.append(
                        ApmEventSource(
                            event_bridge_arn=eb_config.eventbridge_arn,
                            third_party_apm_identifiers=eb_config.alert_identifiers,
                            eventbus_validation_status="SKIPPED",
                            cross_account_warning=False,
                        )
                    )
                    continue

                arn = arnparse(eb_config.eventbridge_arn)

                if arn.service != "events":
                    raise ValueError("Invalid EventBridge ARN format")

                arn_account = extract_account_id_from_arn(eb_config.eventbridge_arn)
                cross_account = arn_account != account_id

                # For same-account EventBridge, validate existence via AWS API
                if not cross_account:
                    try:
                        # Validate using full ARN for non-interactive mode
                        self._eventbridge_accessor.describe_event_bus(
                            arn.region, eb_config.eventbridge_arn
                        )
                        status = "VALIDATED"
                        self.ui.display_info(
                            "    ✅ EventBridge exists and is accessible", style="green"
                        )
                    except Exception as api_error:
                        error_msg = f"EventBridge validation failed: {str(api_error)}"
                        self.ui.display_error(error_msg)
                        validation_failures.append(
                            f"EventBridge {idx} ({eb_config.eventbridge_arn}): {error_msg}"
                        )
                        # Continue to next EventBridge instead of failing completely
                        continue
                else:
                    status = "CROSS_ACCOUNT_WARNING"
                    self.ui.display_warning(
                        "Cross-account EventBridge detected, cannot validate"
                    )

                apm_ingestion_list.append(
                    ApmEventSource(
                        event_bridge_arn=eb_config.eventbridge_arn,
                        third_party_apm_identifiers=eb_config.alert_identifiers,
                        eventbus_validation_status=status,
                        cross_account_warning=cross_account,
                    )
                )

            except Exception as e:
                error_msg = f"APM validation failed: {str(e)}"
                self.ui.display_error(error_msg)
                validation_failures.append(
                    f"EventBridge {idx} ({eb_config.eventbridge_arn}): {error_msg}"
                )
                # Continue to next EventBridge

        if not apm_ingestion_list:
            error_summary = "\n".join(validation_failures)
            raise ValueError(f"All APM validations failed:\n{error_summary}")

        # If some failed, show warning but continue
        if validation_failures:
            self.ui.display_warning(
                f"{len(validation_failures)} EventBridge validation(s) failed. "
                f"Proceeding with {len(apm_ingestion_list)} successful validation(s)."
            )

        return ApmIngestion(
            third_party_apm_identifier_list=apm_ingestion_list,
            workload_contacts=None,
            apm_setup=None,
        )
