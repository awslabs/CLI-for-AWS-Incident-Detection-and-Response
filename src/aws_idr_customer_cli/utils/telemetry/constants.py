from enum import Enum


class MetricUnit(str, Enum):
    """Standard metric units for CloudWatch."""

    Count = "Count"
    Milliseconds = "Milliseconds"
    Seconds = "Seconds"
    Microseconds = "Microseconds"
    Bytes = "Bytes"
    Kilobytes = "Kilobytes"
    Megabytes = "Megabytes"
    Gigabytes = "Gigabytes"
    Percent = "Percent"
    None_ = "None"


class ErrorOrigin(str, Enum):
    """First-level error categorization - WHERE the error came from."""

    USER_INPUT = "UserInput"  # User provided invalid input
    CODE = "CodeError"  # Bug in our code
    DEPENDENCY = "Dependency"  # External system failure
    ENVIRONMENT = "Environment"  # System environment issue
    PERMISSION = "Permission"  # Auth/authorization issue
    UNKNOWN = "Unknown"  # Uncategorized errors


class ErrorType(str, Enum):
    """Second-level categorization - WHAT type of error occurred."""

    # User input errors
    VALIDATION = "Validation"  # Input validation failure
    FORMAT = "Format"  # Wrong format/syntax
    MISSING = "Missing"  # Required parameter missing
    INVALID_OPTION = "InvalidOption"  # Invalid option combination
    INVALID_COMMAND = "InvalidOption"  # Invalid option combination

    # Code errors
    UNHANDLED = "Unhandled"  # Unhandled exception
    IMPLEMENTATION = "Implementation"  # Logic error

    # Dependency errors
    AWS_API = "AwsApi"  # AWS API error
    NETWORK = "Network"  # Network connectivity
    TIMEOUT = "Timeout"  # Operation timed out
    THROTTLING = "Throttling"  # Rate limiting
    SERVICE_ERROR = "ServiceError"  # AWS service returned error

    # Environment errors
    CONFIG = "Configuration"  # Configuration issue
    RESOURCE = "Resource"  # System resource issue (memory, disk)

    # Permission errors
    ACCESS_DENIED = "AccessDenied"  # Access denied
    CREDENTIALS = "Credentials"  # Invalid credentials
