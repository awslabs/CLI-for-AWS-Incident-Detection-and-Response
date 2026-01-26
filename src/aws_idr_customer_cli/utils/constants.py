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
    EVENTBRIDGE = "events"  # boto3 uses "events", not "eventbridge"
    KEYSPACES = "keyspaces"
    LAMBDA = "lambda"
    LOGS = "logs"
    RDS = "rds"
    RESOURCE_GROUPS_TAGGING = "resourcegroupstaggingapi"
    S3 = "s3"
    SNS = "sns"


# Concurrency constants for parallel operations
MAX_PARALLEL_WORKERS = 10  # Conservative worker count to avoid API throttling

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


class MetricType(str, Enum):
    """Metric type classification for alarm templates."""

    NATIVE = "NATIVE"
    CONDITIONAL = "CONDITIONAL"
    NON_NATIVE = "NON-NATIVE"


class AlarmInputMethod(str, Enum):
    TAGS = "tags"
    FILE = "file"
    MANUAL = "manual"


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
