"""Non-interactive workload update service."""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List

from injector import inject

from aws_idr_customer_cli.core.interactive.ui import InteractiveUI
from aws_idr_customer_cli.input.input_resource_discovery import InputResourceDiscovery
from aws_idr_customer_cli.models.non_interactive_config import (
    DiscoveryMethod,
    OutputFormat,
    WorkloadUpdateConfig,
)
from aws_idr_customer_cli.services.file_cache.data import (
    AlarmContacts,
    AlarmIngestion,
    ApmEventSource,
    ApmIngestion,
    CommandStatusTracker,
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
from aws_idr_customer_cli.utils.constants import CLI_VERSION, SCHEMA_VERSION, UpdateType
from aws_idr_customer_cli.utils.log_handlers import CliLogger
from aws_idr_customer_cli.utils.session.session_store import SessionStore
from aws_idr_customer_cli.utils.validation.validator import Validate


class NonInteractiveWorkloadUpdateService(NonInteractiveServiceBase):
    """Service for non-interactive workload update."""

    @inject
    def __init__(
        self,
        ui: InteractiveUI,
        store: SessionStore,
        support_case_service: SupportCaseService,
        input_resource_discovery: InputResourceDiscovery,
        validator: Validate,
        file_cache_service: FileCacheService,
        resource_finder_service: ResourceFinderService,
        logger: CliLogger,
    ) -> None:
        super().__init__(
            ui=ui,
            store=store,
            input_resource_discovery=input_resource_discovery,
            validator=validator,
            support_case_service=support_case_service,
            file_cache_service=file_cache_service,
        )
        self._resource_finder_service = resource_finder_service
        self._logger = logger

    def _display_dry_run_specific_info(self) -> None:
        """Display dry run info specific to workload update."""
        self.ui.display_info("Support case update will be skipped", style="yellow")

    def update_workload_from_config(
        self, config: Dict[str, Any], account_id: str
    ) -> None:
        """Execute complete workload update from config data."""
        config_obj = WorkloadUpdateConfig.from_dict(config)  # type: ignore[attr-defined]
        json_output: Dict[str, Any] = {}
        is_json_mode = config_obj.options.output_format == OutputFormat.JSON
        try:
            submission = self.execute_from_config(config=config, account_id=account_id)
            if is_json_mode:
                json_output["status"] = "success"
                json_output["data"] = self._create_filtered_json_output(submission)
        except Exception as e:
            if is_json_mode:
                json_output["status"] = "failed"
                json_output["error"] = str(e)
            else:
                raise e
        finally:
            if is_json_mode:
                with self.ui.unsilenced_output():
                    self.ui.display_info(
                        json.dumps(json_output, indent=2, ensure_ascii=False)
                    )

    def execute_from_config(
        self, config: Dict[str, Any], account_id: str
    ) -> OnboardingSubmission:
        """Execute workload update from config data."""
        config_obj = WorkloadUpdateConfig.from_dict(config)  # type: ignore[attr-defined]
        self.set_output_format(config_obj.options.output_format)

        # Validate config
        self._validate_config(config_obj)

        # Create submission
        submission = self._create_submission(config_obj, account_id)

        if config_obj.options.dry_run:
            self._display_dry_run_header()
            return submission

        session_id = self.store.create(submission)
        self.store.update(session_id, submission)

        # Create support case with attachment
        case_id = self._support_case_service.create_update_request_case(
            session_id=session_id,
            workload_name=config_obj.workload_name,
            update_type=UpdateType(config_obj.update_type).display_name,
        )

        # Update submission with case ID
        if submission.workload_onboard:
            submission.workload_onboard.support_case_id = case_id
        self.store.update(session_id, submission)

        self.ui.display_info("✅ Update request submitted successfully")
        self.ui.display_info(f"Case ID: {case_id}")

        return submission

    def _create_submission(
        self, config: WorkloadUpdateConfig, account_id: str
    ) -> OnboardingSubmission:
        """Create OnboardingSubmission with data in existing fields."""
        now = datetime.now(timezone.utc)

        # Create progress tracker
        progress = CommandStatusTracker(
            workload_update=ProgressTracker(current_step=4, total_steps=4)
        )

        submission = OnboardingSubmission(
            filehash="non-interactive",
            schema_version=SCHEMA_VERSION,
            idr_cli_version=CLI_VERSION,
            account_id=account_id,
            status=OnboardingStatus.COMPLETED,
            created_at=now,
            last_updated_at=now,
            progress=progress,
            workload_onboard=WorkloadOnboard(
                support_case_id=None,
                name=config.workload_name,
                regions=[],
            ),
        )

        # Add contacts if provided (contacts update)
        if config.update_type == UpdateType.CONTACTS.value and config.contacts:
            submission.alarm_contacts = self._create_alarm_contacts(config.contacts)

        # Add alarms if provided (alarms update)
        if config.update_type == UpdateType.ALARMS.value:
            if config.discovery:
                alarm_arns = self._get_alarm_arns(config)
                if alarm_arns:
                    onboarding_alarms = [
                        OnboardingAlarm(
                            alarm_arn=arn,
                            primary_contact=ContactInfo(name="", email="", phone=""),
                            escalation_contact=ContactInfo(name="", email="", phone=""),
                        )
                        for arn in alarm_arns
                    ]
                    submission.alarm_ingestion = AlarmIngestion(
                        onboarding_alarms=onboarding_alarms,
                        contacts_approval_timestamp=now,
                        workflow_type="update",
                    )

            if config.third_party_apm:
                apm_sources = []
                for source in config.third_party_apm.third_party_apm_identifier_list:
                    apm_sources.append(
                        ApmEventSource(
                            event_bridge_arn=source.eventbridge_arn,
                            third_party_apm_identifiers=source.alert_identifiers,
                            eventbus_validation_status="PENDING",
                        )
                    )
                submission.apm_ingestion = ApmIngestion(
                    third_party_apm_identifier_list=apm_sources
                )

        return submission

    def _create_alarm_contacts(self, contacts_config: Any) -> AlarmContacts:
        """Create alarm contact information from config."""
        primary_contact = ContactInfo(
            name=contacts_config.primary.name,
            email=contacts_config.primary.email,
            phone=contacts_config.primary.phone or "",
        )
        escalation_contact = ContactInfo(
            name=contacts_config.escalation.name,
            email=contacts_config.escalation.email,
            phone=contacts_config.escalation.phone or "",
        )
        return AlarmContacts(
            primary_contact=primary_contact, escalation_contact=escalation_contact
        )

    def _get_alarm_arns(self, config: WorkloadUpdateConfig) -> List[str]:
        """Get alarm ARNs from config (by tags or direct ARNs)."""
        if not config.discovery:
            return []

        if config.discovery.method == DiscoveryMethod.TAGS and config.discovery.tags:
            return self._discover_alarms_by_tags(config)
        elif config.discovery.arns:
            return list(config.discovery.arns)
        return []

    def _validate_config(self, config: WorkloadUpdateConfig) -> None:
        """Validate the configuration."""
        if not config.workload_name:
            raise ValueError("workload_name is required")

        valid_types = (UpdateType.CONTACTS.value, UpdateType.ALARMS.value)
        if config.update_type not in valid_types:
            raise ValueError("update_type must be 'contacts' or 'alarms'")

        if config.update_type == UpdateType.CONTACTS.value and not config.contacts:
            raise ValueError("contacts is required when update_type is 'contacts'")

        if config.update_type == UpdateType.ALARMS.value:
            if not config.discovery and not config.third_party_apm:
                raise ValueError(
                    "discovery or third_party_apm is required "
                    "when update_type is 'alarms'"
                )

    def _discover_alarms_by_tags(self, config: WorkloadUpdateConfig) -> List[str]:
        """Discover alarms by tags."""
        if not config.discovery or not config.discovery.tags:
            return []

        tag_filters = [
            {"Key": k, "Values": [v]} for k, v in config.discovery.tags.items()
        ]

        # Use resource_finder_service directly to avoid interactive prompts
        resources = self._resource_finder_service.find_resources_by_tags(
            tags=tag_filters,
            regions=config.discovery.regions,
            resource_types=["cloudwatch:alarm"],
            resource_label="CloudWatch alarms",
        )

        if not resources:
            return []

        alarm_arns: List[str] = [
            r["ResourceArn"].arn for r in resources if "ResourceArn" in r
        ]
        self._logger.info(f"Discovered {len(alarm_arns)} alarms by tags")
        return alarm_arns
