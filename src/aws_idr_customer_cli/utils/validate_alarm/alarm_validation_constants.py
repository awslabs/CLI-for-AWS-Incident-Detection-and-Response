from enum import Enum
from typing import Final, Set

# Onboarding Status Messages
ONBOARDING_STATUS_APPROVED: Final[str] = (
    "Approved for onboarding - Alarm meets all criteria for IDR incident detection"
)
ONBOARDING_STATUS_REJECTED: Final[str] = (
    "Cannot be onboarded - Alarm does not meet minimum requirements for IDR"
)
ONBOARDING_STATUS_NEEDS_CONFIRMATION: Final[str] = (
    "Needs Customer Confirmation - Alarm requires review and confirmation before onboarding"
)
ONBOARDING_STATUS_VALIDATION_FAILED: Final[str] = (
    "Cannot be onboarded - Validation failed"
)
ONBOARDING_STATUS_COMPOSITE_REVIEW: Final[str] = (
    "Needs Customer Confirmation - This is a composite alarm that requires manual review"
)

# Status Keywords for Detection
STATUS_KEYWORD_APPROVED: Final[str] = "Approved"
STATUS_KEYWORD_CANNOT_ONBOARD: Final[str] = "Cannot be onboarded"

# Alarm Type Constants
ALARM_TYPE_METRIC: Final[str] = "MetricAlarm"
ALARM_TYPE_COMPOSITE: Final[str] = "CompositeAlarm"

# CloudWatch API Constants
CW_ALARM_TYPES_COMPOSITE: Final[str] = "CompositeAlarm"
CW_SERVICE_NAME: Final[str] = "cloudwatch"

# ARN Field Names
ARN_FIELD_ALARM_ARN: Final[str] = "AlarmArn"
ARN_FIELD_ALARM_NAME: Final[str] = "AlarmName"

# Alarm State Values
ALARM_STATE_OK: Final[str] = "OK"
ALARM_STATE_ALARM: Final[str] = "ALARM"
ALARM_STATE_INSUFFICIENT_DATA: Final[str] = "INSUFFICIENT_DATA"

# Alarm Configuration Fields
CONFIG_FIELD_STATE_VALUE: Final[str] = "StateValue"
CONFIG_FIELD_STATE_REASON: Final[str] = "StateReason"
CONFIG_FIELD_STATE_REASON_DATA: Final[str] = "StateReasonData"
CONFIG_FIELD_TREAT_MISSING_DATA: Final[str] = "TreatMissingData"
CONFIG_FIELD_METRICS: Final[str] = "Metrics"
CONFIG_FIELD_NAMESPACE: Final[str] = "Namespace"
CONFIG_FIELD_METRIC_NAME: Final[str] = "MetricName"
CONFIG_FIELD_PERIOD: Final[str] = "Period"
CONFIG_FIELD_ALARM_RULE: Final[str] = "AlarmRule"

# TreatMissingData Values
TREAT_MISSING_DATA_BREACHING: Final[str] = "breaching"

# SQL Expression Keywords
SQL_KEYWORD_SELECT: Final[str] = "SELECT"
SQL_KEYWORD_FROM: Final[str] = "FROM"
SQL_KEYWORD_SCHEMA: Final[str] = "SCHEMA"

# Metric Functions
METRIC_FUNCTION_MAX: Final[str] = "MAX"
METRIC_FUNCTION_MIN: Final[str] = "MIN"
METRIC_FUNCTION_AVG: Final[str] = "AVG"

# State Reason Patterns
STATE_REASON_NO_DATAPOINTS: Final[str] = "no datapoints were received"
STATE_REASON_DATAPOINT: Final[str] = "datapoint"
STATE_REASON_OUT_OF_LAST: Final[str] = "out of the last"
STATE_REASON_THRESHOLD_CROSSED: Final[str] = "threshold crossed:"

# History Summary Patterns
HISTORY_SUMMARY_TO_ALARM: Final[str] = "to ALARM"
HISTORY_SUMMARY_TO_OK: Final[str] = "to OK"

# Alarm Name Prefixes
ALARM_PREFIX_TARGET_TRACKING: Final[str] = "TargetTracking-"

# Default Values
DEFAULT_PERIOD: Final[int] = 300
DEFAULT_PERIOD_RECOMMENDED: Final[int] = 60
DEFAULT_DATAPOINTS_RECOMMENDED: Final[int] = 5
DEFAULT_EVALUATION_PERIODS_RECOMMENDED: Final[int] = 5

# Thresholds
THRESHOLD_PERIOD_MAX: Final[int] = 60
THRESHOLD_DATAPOINTS_MIN: Final[int] = 3
THRESHOLD_EVALUATION_PERIODS_MIN: Final[int] = 3
THRESHOLD_VALUE_CHANGE_PERCENT: Final[float] = 0.2
THRESHOLD_HEALTH_RATIO: Final[float] = 0.6
THRESHOLD_VARIANCE: Final[float] = 0.25
THRESHOLD_MISSING_DATA_RATIO: Final[float] = 0.3

# Time Windows
TIME_WINDOW_LOOKBACK_DAYS: Final[int] = 14
TIME_WINDOW_RECENT_HOURS: Final[int] = 48
TIME_WINDOW_ALARM_PROXIMITY_DAYS: Final[int] = 7
TIME_WINDOW_RAPID_CHANGE_SECONDS: Final[int] = 3600

# Noise Detection Thresholds
NOISE_THRESHOLD_RAPID_CHANGES: Final[int] = 2
NOISE_THRESHOLD_VALUE_SWINGS: Final[int] = 2
NOISE_THRESHOLD_HOURLY_CHANGES: Final[int] = 3
NOISE_THRESHOLD_DAILY_CHANGES: Final[int] = 2
NOISE_THRESHOLD_CONSECUTIVE_MISSING: Final[int] = 3
NOISE_THRESHOLD_DAILY_ALARMS: Final[int] = 2
NOISE_THRESHOLD_STATE_CHANGES: Final[int] = 3

# API Limits
API_MAX_DATAPOINTS_MIN: Final[int] = 10
API_MAX_DATAPOINTS_MAX: Final[int] = 500
API_MAX_RECORDS: Final[int] = 100
API_TOLERANCE_MULTIPLIER: Final[int] = 3

# Critical Metrics by Namespace
CRITICAL_METRICS: Final[dict] = {
    "AWS/RDS": {"DatabaseConnections", "CPUUtilization", "FreeableMemory"},
    "AWS/EC2": {"CPUUtilization", "StatusCheckFailed"},
    "AWS/ElastiCache": {"CPUUtilization", "DatabaseMemoryUsagePercentage"},
    "AWS/FSx": {"DataReadBytes", "DataWriteBytes"},
}

# Unsuitable Metrics
UNSUITABLE_METRICS: Final[Set[str]] = {
    "NetworkIn",
    "NetworkOut",
    "DiskReadOps",
    "DiskWriteOps",
    "DiskReadBytes",
    "DiskWriteBytes",
    "CPUCreditUsage",
}

# Skip Period Check Metrics
SKIP_PERIOD_CHECK_METRICS: Final[Set[str]] = {
    "StatusCheckFailed",
    "StatusCheckFailed_Instance",
    "StatusCheckFailed_System",
}

# Infrastructure Keywords
INFRASTRUCTURE_KEYWORDS: Final[Set[str]] = {
    "disk",
    "memory",
    "cpu",
    "network",
    "storage",
    "filesystem",
    "volume",
    "instance",
    "host",
    "server",
    "infrastructure",
    "system",
}

# Non-Production Keywords
NON_PROD_KEYWORDS: Final[Set[str]] = {
    "dev",
    "test",
    "staging",
    "qa",
    "sandbox",
    "demo",
    "temp",
}


class AlarmTypeEnum(str, Enum):
    """Alarm type enumeration."""

    METRIC = ALARM_TYPE_METRIC
    COMPOSITE = ALARM_TYPE_COMPOSITE


class AlarmStateEnum(str, Enum):
    """Alarm state enumeration."""

    OK = ALARM_STATE_OK
    ALARM = ALARM_STATE_ALARM
    INSUFFICIENT_DATA = ALARM_STATE_INSUFFICIENT_DATA


class MetricFunctionEnum(str, Enum):
    """Metric aggregation function enumeration."""

    MAX = METRIC_FUNCTION_MAX
    MIN = METRIC_FUNCTION_MIN
    AVG = METRIC_FUNCTION_AVG
