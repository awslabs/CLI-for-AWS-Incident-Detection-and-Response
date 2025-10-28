from typing import Set

from aws_idr_customer_cli.utils.log_handlers import CliLogger


class BaseAccessor:
    """Base class for AWS service data accessors with common error handling."""

    # Common AWS error codes that should be treated as validation errors
    VALIDATION_ERRORS: Set[str] = {
        "InvalidParameterException",
        "ValidationError",
        "InvalidParameter",
        "ResourceNotFoundException",
        "StackNotFound",
        "NotFoundException",
    }

    # Common AWS error codes that should be treated as access denied errors
    ACCESS_DENIED_ERRORS: Set[str] = {
        "AccessDeniedException",
        "AccessDenied",
        "UnauthorizedOperation",
    }

    def __init__(self, logger: CliLogger, service_name: str = "AWS API") -> None:
        self.logger = logger
        self.service_name = service_name

    def _handle_error(self, error: Exception, operation: str) -> None:
        """Handle common AWS service errors with consistent error mapping."""

        error_code = (
            getattr(error, "response", {}).get("Error", {}).get("Code", "Unknown")
        )

        if error_code == "ValidationError" and operation == "describe_stacks":
            self.logger.debug(
                f"Stack not found in {operation}: {error_code} - {str(error)}"
            )
        else:
            self.logger.error(f"Error in {operation}: {error_code} - {str(error)}")

        if error_code in self.ACCESS_DENIED_ERRORS:
            raise PermissionError(f"Access denied to {self.service_name}: {str(error)}")
        elif error_code in self.VALIDATION_ERRORS:
            raise ValueError(f"Invalid parameters provided: {str(error)}")
        else:
            raise error
