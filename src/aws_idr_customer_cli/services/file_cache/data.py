from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from dataclasses_json import DataClassJsonMixin, config, dataclass_json
from dateutil.parser import isoparse
from marshmallow import fields

from aws_idr_customer_cli.utils.constants import DiscoverMethod


def datetime_field(required: bool = True) -> Any:
    """Create a datetime field with consistent JSON serialization."""
    if required:
        return field(
            metadata=config(
                encoder=datetime.isoformat,
                decoder=isoparse,
                mm_field=fields.DateTime(format="iso"),
            )
        )
    else:
        return field(
            default=None,
            metadata=config(
                encoder=lambda x: x.isoformat() if x else None,
                decoder=lambda x: isoparse(x) if x else None,
                mm_field=fields.DateTime(format="iso", allow_none=True),
            ),
        )


class OnboardingStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


@dataclass_json
@dataclass
class ProgressTracker:
    current_step: int = 0
    total_steps: int = 0
    step_name: str = ""
    completed_steps: List[str] = field(default_factory=list)


@dataclass_json
@dataclass
class CommandStatusTracker(DataClassJsonMixin):
    """Container for all progress trackers by phase."""

    workload_registration: Optional[ProgressTracker] = None
    alarm_creation: Optional[ProgressTracker] = None
    alarm_ingestion: Optional[ProgressTracker] = None
    apm_setup: Optional[ProgressTracker] = None


@dataclass_json
@dataclass
class ResourceArn:
    type: str
    arn: str
    region: str
    name: Optional[str] = None


@dataclass_json
@dataclass
class ContactInfo:
    name: str
    email: str
    phone: str = ""


@dataclass_json
@dataclass
class AlarmContacts:
    primary_contact: ContactInfo
    escalation_contact: ContactInfo


@dataclass_json
@dataclass
class WorkloadOnboard:
    support_case_id: Optional[str]
    name: str
    regions: List[str]
    contacts_approval_timestamp: Optional[datetime] = datetime_field(required=False)
    # Deprecated fields - for backward compatibility only
    description: Optional[str] = None
    enterprise_name: Optional[str] = None


@dataclass_json
@dataclass
class AlarmConfiguration:
    alarm_name: str


@dataclass_json
@dataclass
class AlarmCreation:
    alarm_arn: Optional[str]
    is_selected: bool
    already_exists: Optional[bool]
    resource_arn: Optional[ResourceArn]
    alarm_configuration: AlarmConfiguration
    successful: Optional[bool] = None
    created_at: Optional[datetime] = datetime_field(required=False)


@dataclass_json
@dataclass
class AlarmValidation:
    alarm_arn: str
    onboarding_status: str = "N"
    is_noisy: bool = False
    remarks_for_customer: List[str] = field(default_factory=list)
    remarks_for_idr: List[str] = field(default_factory=list)
    noise_analysis: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_validation_passed(self) -> bool:
        """Backward compatibility property."""
        return self.onboarding_status == "Y" or "Approved" in self.onboarding_status


@dataclass_json
@dataclass
class Contact:
    id: int
    name: str
    phone: str
    email: str


@dataclass_json
@dataclass
class Escalation:
    sequence: List[int]
    time: int


@dataclass_json
@dataclass
class OnboardingAlarm:
    alarm_arn: str
    primary_contact: ContactInfo
    escalation_contact: ContactInfo


@dataclass_json
@dataclass
class AlarmIngestion:
    onboarding_alarms: List[OnboardingAlarm]
    contacts_approval_timestamp: datetime = datetime_field(required=True)
    workflow_type: Optional[str] = None


@dataclass_json
@dataclass
class ApmEventSource:
    """Single EventBridge event source with validation status.
    Represents one APM data source (EventBridge) with its alert identifiers.
    """

    event_bridge_arn: str
    third_party_apm_identifiers: List[str]
    eventbus_validation_status: str = "PENDING"
    cross_account_warning: bool = False


@dataclass_json
@dataclass
class ApmIngestion:
    """APM alert ingestion data with support for multiple EventBridge ARNs."""

    third_party_apm_identifier_list: List[ApmEventSource]
    workload_contacts: Optional[AlarmContacts] = None
    apm_setup: Optional[Any] = None


@dataclass_json
@dataclass
class ApmSetup:
    provider: str
    deployment_region: str

    partner_event_source_arn: Optional[str] = None
    sns_topic_arn: Optional[str] = None
    custom_incident_path: Optional[str] = None
    alert_identifiers: Optional[List[str]] = None
    resources: Optional[Dict[str, Any]] = None

    support_case_id: Optional[str] = None
    deployment_successful: Optional[bool] = None
    configured_at: Optional[datetime] = datetime_field(required=False)


@dataclass_json
@dataclass
class OnboardingSubmission(DataClassJsonMixin):
    filehash: str
    schema_version: str
    idr_cli_version: str
    account_id: str
    status: OnboardingStatus

    created_at: datetime = datetime_field(required=True)
    last_updated_at: datetime = datetime_field(required=True)
    session_count: int = 1
    execution_mode: Optional[str] = None

    progress: CommandStatusTracker = field(default_factory=CommandStatusTracker)
    progress_tracker: ProgressTracker = field(default_factory=ProgressTracker)
    resource_arns_selected: Optional[List[ResourceArn]] = None
    resource_discovery_methods: Optional[List[DiscoverMethod]] = None
    resource_tags: Optional[List[Dict[str, Any]]] = None
    workload_onboard: Optional[WorkloadOnboard] = None
    alarm_contacts: Optional[AlarmContacts] = None
    workload_to_alarm_handoff: bool = False
    alarm_creation: Optional[List[AlarmCreation]] = None
    alarm_validation: Optional[List[AlarmValidation]] = None
    alarm_ingestion: Optional[AlarmIngestion] = None
    # Deprecated field - for backward compatibility only
    workload_contacts: Optional[AlarmContacts] = None

    apm_setup: Optional[ApmSetup] = None
    apm_ingestion: Optional[ApmIngestion] = None
