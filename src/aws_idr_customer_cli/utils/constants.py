from enum import Enum
from importlib.metadata import PackageNotFoundError, version

# Version constants
SCHEMA_VERSION = "2"


class BotoServiceName(str, Enum):
    """AWS boto3 service names for SDK client creation.

    These are the service names passed to boto3.client() for creating
    AWS service clients. Note that some service names differ from their
    common names (e.g., EventBridge uses "events", not "eventbridge").
    """

    CLOUDFORMATION = "cloudformation"
    CLOUDFRONT = "cloudfront"
    CLOUDWATCH = "cloudwatch"
    DYNAMODB = "dynamodb"
    EMR = "emr"
    EVENTBRIDGE = "events"  # boto3 uses "events", not "eventbridge"
    KAFKA = "kafka"
    KEYSPACES = "keyspaces"
    LAMBDA = "lambda"
    LOGS = "logs"
    OPENSEARCH = "opensearch"
    RDS = "rds"
    RESOURCE_GROUPS_TAGGING = "resourcegroupstaggingapi"
    S3 = "s3"
    SNS = "sns"


# Concurrency constants for parallel operations
MAX_PARALLEL_WORKERS = 10  # Conservative worker count to avoid API throttling

# Regions skipped during best-effort multi-region metric scans (e.g. Lambda@Edge).
# These regions have had sustained endpoint reachability issues that cause
# 5+ minute hangs on default boto3 connect/read timeouts. Customers running
# Lambda@Edge in these regions should re-run after AWS service health recovers.
LAMBDA_EDGE_SCAN_REGION_DENYLIST = frozenset({"me-south-1", "me-central-1"})

# Aggressive timeouts used only by best-effort multi-region metric scans.
# A single unreachable region must not stall the whole scan: budget per region
# is ~connect_timeout + read_timeout * (max_attempts - 1) seconds.
SCAN_CONNECT_TIMEOUT_SECONDS = 3
SCAN_READ_TIMEOUT_SECONDS = 10
SCAN_MAX_ATTEMPTS = 2

try:
    CLI_VERSION = version("awsidr")
except PackageNotFoundError:
    CLI_VERSION = version("amzn-idr-cli")


class DiscoverMethod(str, Enum):
    TAG = "Tag"


class CommandType(str, Enum):
    WORKLOAD_REGISTRATION = "workload_registration"
    ALARM_CREATION = "alarm_creation"
    ALARM_INGESTION = "alarm_ingestion"
    APM_SETUP = "apm_setup"
    WORKLOAD_UPDATE = "workload_update"


class MetricType(str, Enum):
    """Metric type classification for alarm templates."""

    NATIVE = "NATIVE"
    CONDITIONAL = "CONDITIONAL"
    NON_NATIVE = "NON-NATIVE"


class MskBrokerType(str, Enum):
    """MSK broker type for provisioned clusters."""

    STANDARD = "STANDARD"
    EXPRESS = "EXPRESS"


class AlarmInputMethod(str, Enum):
    TAGS = "tags"
    FILE = "file"
    MANUAL = "manual"


class UpdateType(str, Enum):
    """Update types for update-workload command."""

    CONTACTS = "contacts"
    ALARMS = "alarms"

    @property
    def display_name(self) -> str:
        """Display name for UI."""
        if self == UpdateType.CONTACTS:
            return "Contacts/Escalation"
        return "Alarms"


# Default AWS region
DEFAULT_REGION = "us-east-1"


class SessionKeys(str, Enum):
    WORKFLOW_COMPLETED = "workflow_completed"
    ALARM_CREATION = "alarm_creation"


class ItemType(str, Enum):
    RESOURCE = "resource"
    ALARM = "alarm"


# Mock account ID for testing
MOCK_ACCOUNT_ID = "123456789012"


class Region(str, Enum):
    US_EAST_1 = "us-east-1"
    GLOBAL_REGION = "global"
