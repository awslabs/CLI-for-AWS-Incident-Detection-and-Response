from enum import Enum
from importlib.metadata import PackageNotFoundError, version

# Version constants
SCHEMA_VERSION = "2"
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
