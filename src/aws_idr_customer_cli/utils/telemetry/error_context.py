import os
import sys
import traceback
from typing import Any, Dict, List, Optional, Union

from aws_idr_customer_cli.utils.telemetry.constants import ErrorOrigin, ErrorType


class ErrorContext:
    """
    Captures structured error context for telemetry and troubleshooting.

    Provides utilities to categorize errors, extract relevant information,
    and create a structured representation suitable for metrics and logging.
    """

    @staticmethod
    def capture(
        exception: BaseException,
        origin: Optional[ErrorOrigin] = None,
        error_type: Optional[ErrorType] = None,
        command: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Capture comprehensive error context as a structured dictionary.

        Args:
            exception: The exception that was raised
            origin: Optional override for error origin category
            error_type: Optional override for error type
            command: The command being executed when error occurred
            metadata: Additional context data to include

        Returns:
            Structured dictionary with error context information

        Example:
            ```python
            try:
                result = api_client.call_operation()
            except Exception as e:
                error_context = ErrorContext.capture(
                    e, command="update-resource",
                    metadata={"resource_id": resource_id}
                )
                logger.error("Operation failed", extra={"error_context": error_context})
            ```
        """
        # Auto-categorize if not provided
        if origin is None or error_type is None:
            auto_origin, auto_type = ErrorContext._categorize_exception(exception)
            origin = origin or auto_origin
            error_type = error_type or auto_type

        # Simplified stack trace collection - get basic info without complex filtering
        frames = ErrorContext._get_simple_frames(exception)

        # Build the context dictionary
        context = {
            "error": {
                "message": str(exception),
                "type": type(exception).__name__,
                "origin": origin,
                "error_type": error_type,
                "traceback": frames,
                "module": exception.__class__.__module__,
            },
            "command": {
                "name": command,
                "args": sys.argv[1:] if len(sys.argv) > 1 else [],
            },
            "environment": {
                "python_version": sys.version.split()[0],  # Just get version number
                "os": os.name,
                "region": os.environ.get("AWS_REGION", "unknown"),
            },
        }

        # Add custom metadata
        if metadata:
            context["metadata"] = metadata

        return context

    @staticmethod
    def _categorize_exception(
        exception: BaseException,
    ) -> tuple[ErrorOrigin, ErrorType]:
        """
        Automatically categorize an exception by origin and type.

        Args:
            exception: The exception to categorize

        Returns:
            Tuple of (ErrorOrigin, ErrorType) enum values
        """
        ex_type = type(exception)
        ex_str = str(exception).lower()

        # User input errors
        if ex_type in (ValueError, TypeError, KeyError, AttributeError):
            return ErrorOrigin.USER_INPUT, ErrorType.VALIDATION

        # AWS service errors - check for boto3/botocore
        if "botocore.exceptions" in str(ex_type.__module__):
            if "AccessDenied" in ex_type.__name__:
                return ErrorOrigin.PERMISSION, ErrorType.ACCESS_DENIED
            elif "NoCredentials" in ex_type.__name__:
                return ErrorOrigin.PERMISSION, ErrorType.CREDENTIALS
            elif (
                "Throttling" in ex_type.__name__
                or "TooManyRequests" in ex_type.__name__
            ):
                return ErrorOrigin.DEPENDENCY, ErrorType.THROTTLING
            else:
                return ErrorOrigin.DEPENDENCY, ErrorType.AWS_API

        # Network errors
        if isinstance(exception, (ConnectionError, TimeoutError)):
            return ErrorOrigin.DEPENDENCY, ErrorType.NETWORK

        # Look at the error message
        if any(x in ex_str for x in ["permission", "access denied"]):
            return ErrorOrigin.PERMISSION, ErrorType.ACCESS_DENIED
        if any(x in ex_str for x in ["credential", "auth"]):
            return ErrorOrigin.PERMISSION, ErrorType.CREDENTIALS
        if "not found" in ex_str:
            return ErrorOrigin.USER_INPUT, ErrorType.MISSING

        # Default case
        return ErrorOrigin.CODE, ErrorType.UNHANDLED

    @staticmethod
    def _get_simple_frames(
        exception: BaseException,
    ) -> List[Dict[str, Union[str, int]]]:
        """
        Extract simplified frame information from the exception traceback.

        This internal method processes the traceback from an exception and
        returns a list of simplified frame information dictionaries.

        Args:
            exception: The exception containing the traceback

        Returns:
            List of dictionaries with basic frame information

        Example:
            ```python
            # For an exception like:
            try:
                def outer():
                    def inner():
                        raise ValueError("Invalid input")
                    inner()
                outer()
            except ValueError as e:
                # This method would extract frames like:
                frames = [
                    {
                        "file": "example.py",
                        "line": 4,
                        "function": "inner"
                    },
                    {
                        "file": "example.py",
                        "line": 5,
                        "function": "outer"
                    },
                    # ...other frames
                ]
                # These frames become part of the structured error context
                # for error analysis and reporting
            ```
        """
        frames = []
        tb = traceback.extract_tb(sys.exc_info()[2]) if sys.exc_info()[2] else []

        for frame in tb:
            # Create dictionary with all potential values
            frame_dict = {
                "file": os.path.basename(frame.filename),
                "line": frame.lineno,
                "function": frame.name,
            }

            # Filter out None values
            filtered_dict = {k: v for k, v in frame_dict.items() if v is not None}
            frames.append(filtered_dict)

        return frames
