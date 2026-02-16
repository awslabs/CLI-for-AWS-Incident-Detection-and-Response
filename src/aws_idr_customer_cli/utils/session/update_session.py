from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from aws_idr_customer_cli.services.file_cache.data import (
    AlarmIngestion,
    ApmEventSource,
    ApmIngestion,
    ContactInfo,
    OnboardingAlarm,
    WorkloadOnboard,
)
from aws_idr_customer_cli.services.support_case_service import SupportCaseService
from aws_idr_customer_cli.utils.alarm_contact_collection import (
    collect_alarm_contact_info,
    display_alarm_contact_summary,
)
from aws_idr_customer_cli.utils.constants import (
    DEFAULT_REGION,
    AlarmInputMethod,
    CommandType,
)
from aws_idr_customer_cli.utils.resource_discovery_utils import (
    collect_manual_alarm_arns,
)
from aws_idr_customer_cli.utils.session.interactive_session import (
    ACTION_KEY,
    ACTION_PAUSE,
    MSG_RESUMING_SESSION,
    STYLE_BLUE,
    STYLE_DIM,
    InteractiveSession,
    session_step,
)
from aws_idr_customer_cli.utils.session.session_store import SessionStore
from aws_idr_customer_cli.utils.workload_meta_data_collection_utils import (
    collect_regions,
)

UPDATE_TYPE_CONTACTS = "Contacts/Escalation"
UPDATE_TYPE_ALARMS = "Alarms"
UPDATE_OPTIONS = [UPDATE_TYPE_CONTACTS, UPDATE_TYPE_ALARMS]

ALARM_TYPE_CLOUDWATCH = "CloudWatch Alarms"
ALARM_TYPE_APM = "APM Alarms (eg. Datadog, New Relic etc.)"
ALARM_TYPE_OPTIONS = [ALARM_TYPE_CLOUDWATCH, ALARM_TYPE_APM]


class UpdateSession(InteractiveSession):
    """Interactive session for workload update requests."""

    def __init__(
        self,
        store: SessionStore,
        support_case_service: SupportCaseService,
        validator: Any,
        input_resource_discovery: Any,
        account_id: str,
        resume_session_id: Optional[str] = None,
    ) -> None:
        self._support_case_service = support_case_service
        self._validator = validator
        self._input_resource_discovery = input_resource_discovery
        self._alarm_type: Optional[str] = None
        self._workload_name: str = ""
        self._update_type: str = ""
        super().__init__(
            CommandType.WORKLOAD_UPDATE, account_id, store, resume_session_id
        )

    @session_step("Enter Workload Name", order=1)
    def collect_workload_name(self) -> Dict[str, Any]:
        """Collect workload name."""
        # Check if we have existing workload name
        if self.submission.workload_onboard and self.submission.workload_onboard.name:
            self._workload_name = self.submission.workload_onboard.name
            self.ui.display_info(f"Current workload: {self._workload_name}")
            if not self.ui.prompt_confirm("Change workload name?", default=False):
                return {}

        default_name = self._workload_name or None
        name = self.ui.prompt_input("Enter the workload name", default=default_name)

        if not name.strip():
            self.ui.display_error("Workload name cannot be empty")
            return {ACTION_KEY: "retry"}

        self._workload_name = name.strip()
        # Store in workload_onboard for file cache
        if not self.submission.workload_onboard:
            self.submission.workload_onboard = WorkloadOnboard(
                support_case_id=None, name=self._workload_name, regions=[]
            )
        else:
            self.submission.workload_onboard.name = self._workload_name
        self._save_progress()
        self.ui.display_info(f"✅ Workload: {self._workload_name}")
        return {}

    @session_step("Select Update Type", order=2)
    def select_update_type(self) -> Dict[str, Any]:
        """Select what to update."""
        self.ui.display_header("Update Type Selection", "Select what to update:")
        idx = self.ui.select_option(UPDATE_OPTIONS, "Available update options")
        self._update_type = UPDATE_OPTIONS[idx]
        self._save_progress()
        self.ui.display_info(f"✅ Update type: {self._update_type}")
        return {}

    @session_step("Enter Update Details", order=3)
    def collect_details(self) -> Dict[str, Any]:
        """Collect update details - contacts or alarms."""
        if self._update_type == UPDATE_TYPE_CONTACTS:
            return self._collect_contact_details()
        else:
            return self._collect_alarm_details()

    def _collect_contact_details(self) -> Dict[str, Any]:
        """Collect contact update details into alarm_contacts."""
        self.ui.display_info(
            "📞 Collecting updated primary and escalation contact information"
        )
        success = collect_alarm_contact_info(self.ui, self.submission)
        if not success:
            return {ACTION_KEY: "retry"}
        self._save_progress()
        return {}

    def _collect_alarm_details(self) -> Dict[str, Any]:
        """Collect alarm update details - CW or APM."""
        self.ui.display_info("🔔 What type of alarms would you like to add?")
        idx = self.ui.select_option(ALARM_TYPE_OPTIONS, "Select alarm type")
        self._alarm_type = ALARM_TYPE_OPTIONS[idx]

        if self._alarm_type == ALARM_TYPE_CLOUDWATCH:
            return self._collect_cloudwatch_alarms()
        else:
            return self._collect_apm_alarms()

    def _collect_cloudwatch_alarms(self) -> Dict[str, Any]:
        """Collect CloudWatch alarm ARNs into alarm_ingestion."""
        self.ui.display_info("How would you like to provide alarm ARNs?")
        options = [
            "Find alarms by tags",
            "Upload a text file with ARNs",
            "Enter ARNs manually",
        ]
        choice = self.ui.select_option(options, "Select input method")

        alarm_arns: List[str] = []
        regions: List[str] = []

        if choice == 0:
            # Tag-based discovery
            self.ui.display_info("📍 Select regions to search for alarms")
            regions = collect_regions(self.ui)
            if not regions:
                regions = [DEFAULT_REGION]

            result = self._input_resource_discovery.discover_alarms_by_tags(
                regions=regions
            )
            if isinstance(result, dict):
                return result

            alarm_arns, _ = result
            self.ui.display_info(
                f"✅ Found {len(alarm_arns)} alarm(s) matching tag criteria"
            )
        else:
            # File or manual input
            input_method = (
                AlarmInputMethod.FILE if choice == 1 else AlarmInputMethod.MANUAL
            )
            result = collect_manual_alarm_arns(
                ui=self.ui,
                validator=self._validator,
                input_method=str(input_method.value),
            )
            if isinstance(result, dict):
                return result

            alarm_arns = result
            self.ui.display_info(f"✅ Collected {len(alarm_arns)} alarm ARN(s)")

            # Extract regions from ARNs (same as alarm_ingestion_session)
            from aws_idr_customer_cli.utils.arn_utils import build_resource_arn_object

            region_set: set[str] = set()
            for arn in alarm_arns:
                try:
                    resource_arn = build_resource_arn_object(arn)
                    if resource_arn.region and resource_arn.region != "global":
                        region_set.add(resource_arn.region)
                except Exception:
                    pass
            regions = sorted(list(region_set))
            if regions:
                self.ui.display_info(f"📍 Detected regions: {', '.join(regions)}")

        # Store alarm_arns on submission (same as alarm_ingestion_session)
        self.submission.alarm_arns = alarm_arns

        # Store regions in workload_onboard
        if self.submission.workload_onboard:
            self.submission.workload_onboard.regions = regions

        # Store in alarm_ingestion with workflow_type="update"
        onboarding_alarms = [
            OnboardingAlarm(
                alarm_arn=arn,
                primary_contact=ContactInfo(name="", email="", phone=""),
                escalation_contact=ContactInfo(name="", email="", phone=""),
            )
            for arn in alarm_arns
        ]
        self.submission.alarm_ingestion = AlarmIngestion(
            onboarding_alarms=onboarding_alarms,
            contacts_approval_timestamp=datetime.now(timezone.utc),
            workflow_type="update",
        )
        self._save_progress()
        return {}

    def _collect_apm_alarms(self) -> Dict[str, Any]:
        """Collect APM alarm details into apm_ingestion."""
        self.ui.display_info("📡 APM Alarm Configuration")

        # Collect region for EventBridge (same as alarm_ingestion_session)
        self.ui.display_info(
            "📍 Enter the region where your CustomEventBus is deployed"
        )
        regions = collect_regions(self.ui, single_region=True)
        if not regions:
            regions = [DEFAULT_REGION]
        if self.submission.workload_onboard:
            self.submission.workload_onboard.regions = regions

        # Collect EventBridge ARN
        self.ui.display_info(
            "Enter the EventBridge CustomEventBus ARN from your APM CloudFormation stack"
        )
        eventbus_arn = self.ui.prompt_input("EventBridge event bus ARN")
        if not eventbus_arn.strip():
            self.ui.display_error("EventBridge ARN cannot be empty")
            return {ACTION_KEY: "retry"}

        # Collect APM identifiers
        self.ui.display_info(
            "Enter comma-separated alert identifiers that your APM sends "
            "(e.g., 'error-counts,cpu-utilization,latency')"
        )
        identifiers_input = self.ui.prompt_input("Alert identifiers")
        identifiers = [i.strip() for i in identifiers_input.split(",") if i.strip()]

        if not identifiers:
            self.ui.display_error("At least one alert identifier is required")
            return {ACTION_KEY: "retry"}

        # Store in apm_ingestion (same structure as ingest-alarms APM)
        apm_source = ApmEventSource(
            event_bridge_arn=eventbus_arn.strip(),
            third_party_apm_identifiers=identifiers,
            eventbus_validation_status="PENDING",
        )
        self.submission.apm_ingestion = ApmIngestion(
            third_party_apm_identifier_list=[apm_source]
        )
        self.ui.display_info(f"✅ Configured {len(identifiers)} alert identifier(s)")
        self._save_progress()
        return {}

    @session_step("Review and Submit", order=4)
    def submit_request(self) -> Dict[str, Any]:
        """Review and submit the update request."""
        self.ui.display_header("Review Update Request")

        # Show contact summary if contacts update
        if self._update_type == UPDATE_TYPE_CONTACTS and self.submission.alarm_contacts:
            display_alarm_contact_summary(self.ui, self.submission)
        elif self._update_type == UPDATE_TYPE_ALARMS:
            self._display_alarm_summary()

        if not self.ui.prompt_confirm("Submit this update request?", default=True):
            self.ui.display_warning("Update request cancelled")
            return {ACTION_KEY: ACTION_PAUSE}

        self.ui.display_info("📤 Submitting update request...")
        self._save_progress()
        case_id = self._create_support_case()

        # Store case ID in workload_onboard
        if self.submission.workload_onboard:
            self.submission.workload_onboard.support_case_id = case_id
        self._save_progress()

        self._display_support_case(case_id)
        return {}

    def _display_alarm_summary(self) -> None:
        """Display alarm update summary."""
        if self.submission.alarm_ingestion:
            alarms = self.submission.alarm_ingestion.onboarding_alarms
            self.ui.display_result(
                "CloudWatch Alarms to Add",
                {"Count": len(alarms), "ARNs": [a.alarm_arn for a in alarms[:5]]},
            )
            if len(alarms) > 5:
                self.ui.display_info(f"... and {len(alarms) - 5} more")
        elif self.submission.apm_ingestion:
            sources = self.submission.apm_ingestion.third_party_apm_identifier_list
            for src in sources:
                self.ui.display_result(
                    "APM Alarms to Add",
                    {
                        "EventBridge ARN": src.event_bridge_arn,
                        "Identifiers": src.third_party_apm_identifiers,
                    },
                )

    def _create_support_case(self) -> str:
        """Create support case for update request."""
        case_id: str = self._support_case_service.create_update_request_case(
            session_id=self.session_id,
            workload_name=self._workload_name,
            update_type=self._update_type,
        )
        return case_id

    def _display_support_case(self, case_id: str) -> None:
        """Display support case info."""
        try:
            case = self._support_case_service.describe_case(case_id)
            self.ui.display_result(
                "📋 Support Case Created",
                {
                    "Case ID": case.get("displayId", case_id),
                    "Status": case.get("status", "Open"),
                },
            )
        except Exception:
            self.ui.display_info(f"📋 Support Case ID: {case_id}")

    def _display_resume_info(self) -> None:
        """Display resume information."""
        if not self.submission:
            return

        self.ui.display_info(
            MSG_RESUMING_SESSION.format(self.current_step + 1, len(self.steps)),
            style=STYLE_BLUE,
        )

        if self.submission.workload_onboard and self.submission.workload_onboard.name:
            self._workload_name = self.submission.workload_onboard.name
            self.ui.display_info(f"📋 Workload: {self._workload_name}", style=STYLE_DIM)
