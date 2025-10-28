from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from dataclasses_json import dataclass_json


class DiscoveryMethod(str, Enum):
    TAGS = "tags"
    ARNS = "arns"


class OutputFormat(str, Enum):
    TEXT = "text"
    JSON = "json"


@dataclass_json
@dataclass
class WorkloadConfig:
    name: str
    regions: List[str] = field(default_factory=list)  # Optional for ARN-based discovery


@dataclass_json
@dataclass
class DiscoveryConfig:
    method: DiscoveryMethod
    tags: Optional[Dict[str, str]] = None
    arns: Optional[List[str]] = None


@dataclass_json
@dataclass
class AlarmContactConfig:
    """Contact configuration for alarm contacts."""

    name: str
    email: str
    phone: Optional[str] = None


@dataclass_json
@dataclass
class AlarmContactsConfig:
    """Alarm contacts configuration with primary and optional escalation."""

    primary: AlarmContactConfig
    escalation: Optional[AlarmContactConfig] = None


@dataclass_json
@dataclass
class WorkloadRegistrationOptionsConfig:
    dry_run: bool = False
    output_format: OutputFormat = OutputFormat.TEXT


@dataclass_json
@dataclass
class AlarmSelectionConfig:
    """Configuration for alarm selection preferences."""

    resource_types: Optional[List[str]] = (
        None  # Resource types to filter by (e.g., ["lambda", "ec2"])
    )


@dataclass_json
@dataclass
class AlarmCreationOptionsConfig:
    """Options for alarm creation process."""

    create_support_case: bool = True
    update_existing_case: bool = True
    create_service_linked_role: bool = True
    dry_run: bool = False
    output_format: OutputFormat = OutputFormat.TEXT


@dataclass_json
@dataclass
class WorkloadRegistrationConfig:
    workload: WorkloadConfig
    discovery: DiscoveryConfig
    options: WorkloadRegistrationOptionsConfig = field(
        default_factory=WorkloadRegistrationOptionsConfig
    )


@dataclass_json
@dataclass
class AlarmCreationConfig:
    """Complete configuration for non-interactive alarm creation."""

    workload: WorkloadConfig
    contacts: AlarmContactsConfig
    discovery: DiscoveryConfig
    alarm_selection: AlarmSelectionConfig = field(default_factory=AlarmSelectionConfig)
    options: AlarmCreationOptionsConfig = field(
        default_factory=AlarmCreationOptionsConfig
    )


@dataclass_json
@dataclass
class AlarmIngestionOptionsConfig:
    """Options for alarm ingestion process."""

    create_support_case: bool = True
    update_existing_case: bool = True
    create_service_linked_role: bool = True
    dry_run: bool = False
    output_format: OutputFormat = OutputFormat.TEXT


@dataclass_json
@dataclass
class ApmEventSourceConfig:
    """Configuration for a single APM event source (EventBridge) with its alert identifiers."""

    eventbridge_arn: str
    alert_identifiers: List[str]


@dataclass_json
@dataclass
class ApmConfig:
    """Configuration for Third-Party APM integration with multiple EventBridge ARNs."""

    third_party_apm_identifier_list: List[ApmEventSourceConfig]


@dataclass_json
@dataclass
class AlarmIngestionConfig:
    """Complete configuration for non-interactive alarm ingestion."""

    workload: WorkloadConfig
    contacts: AlarmContactsConfig
    discovery: Optional[DiscoveryConfig] = None
    third_party_apm: Optional[ApmConfig] = None
    options: AlarmIngestionOptionsConfig = field(
        default_factory=AlarmIngestionOptionsConfig
    )
