from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from dataclasses_json import DataClassJsonMixin, config, dataclass_json
from dateutil.parser import isoparse
from marshmallow import fields

from aws_idr_customer_cli.utils.constants import DiscoverMethod


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
    contacts_approval_timestamp: Optional[datetime] = field(
        default=None,
        metadata=config(
            encoder=lambda x: x.isoformat() if x is not None else None,
            decoder=lambda x: isoparse(x) if x is not None else None,
            mm_field=fields.DateTime(format="iso", allow_none=True),
        ),
    )
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
    created_at: Optional[datetime] = field(
        default=None,
        metadata=config(
            encoder=lambda x: x.isoformat() if x is not None else None,
            decoder=lambda x: isoparse(x) if x is not None else None,
            mm_field=fields.DateTime(format="iso", allow_none=True),
        ),
    )


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
    contacts_approval_timestamp: datetime = field(
        metadata=config(
            encoder=datetime.isoformat,
            decoder=isoparse,
            mm_field=fields.DateTime(format="iso"),
        )
    )


@dataclass_json
@dataclass
class OnboardingSubmission(DataClassJsonMixin):
    filehash: str
    schema_version: str
    idr_cli_version: str
    account_id: str
    status: OnboardingStatus
    created_at: datetime = field(
        metadata=config(
            encoder=datetime.isoformat,
            decoder=isoparse,
            mm_field=fields.DateTime(format="iso"),
        )
    )
    last_updated_at: datetime = field(
        metadata=config(
            encoder=datetime.isoformat,
            decoder=isoparse,
            mm_field=fields.DateTime(format="iso"),
        )
    )
    progress: CommandStatusTracker = field(default_factory=CommandStatusTracker)
    progress_tracker: ProgressTracker = field(default_factory=ProgressTracker)
    resource_arns_selected: Optional[List[ResourceArn]] = None
    resource_discovery_methods: Optional[List[DiscoverMethod]] = None
    resource_tags: Optional[List[Dict[str, Any]]] = None
    workload_onboard: Optional[WorkloadOnboard] = None
    alarm_contacts: Optional[AlarmContacts] = None
    workload_to_alarm_handoff: bool = False
    alarm_arns: Optional[List[str]] = None
    alarm_creation: Optional[List[AlarmCreation]] = None
    alarm_validation: Optional[List[AlarmValidation]] = None
    alarm_ingestion: Optional[AlarmIngestion] = None
    # Deprecated field - for backward compatibility only
    workload_contacts: Optional[AlarmContacts] = None
