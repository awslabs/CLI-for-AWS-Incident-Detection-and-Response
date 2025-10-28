import functools
import hashlib
import os
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Callable, Dict, Generator, Optional, TypeVar, Union, cast

from injector import inject, singleton

from aws_idr_customer_cli.utils.log_handlers import CliLogger
from aws_idr_customer_cli.utils.telemetry.constants import (
    ErrorOrigin,
    ErrorType,
    MetricUnit,
)
from aws_idr_customer_cli.utils.telemetry.error_context import ErrorContext

T = TypeVar("T", bound=Callable[..., Any])

DEFAULT_NAMESPACE = "AWS/IDR/CLI"


@singleton
class Telemetry:
    """
    CLI-focused telemetry system that collects metrics about command
    execution and delivers them to CloudWatch via EMF format.

    This implementation is specifically designed for CLI tools with:
    - Immediate metric delivery (no background threads)
    - Command-focused context
    - Layered error triage
    - CloudWatch dashboard compatibility
    """

    @inject
    def __init__(self, logger: CliLogger):
        """Initialize with injected logger."""
        self.logger = logger
        self.default_namespace = DEFAULT_NAMESPACE

        # Command context
        self.command_name: Optional[str] = None
        self.subcommand_name: Optional[str] = None
        self.command_dimensions: Dict[str, str] = {}

        # for uniqueness per CLI execution
        self.invocation_id = hashlib.md5(
            f"{datetime.now().isoformat()}-{os.getpid()}".encode()
        ).hexdigest()[:8]

    def track(
        self,
        namespace: Optional[str] = None,
        operation: Optional[str] = None,
        dimensions: Optional[Dict[str, str]] = None,
    ) -> Callable[[T], T]:
        """
        Decorator to track function execution metrics.

        Args:
            namespace: CloudWatch namespace
            operation: Operation name
            dimensions: Additional dimensions

        Returns:
            Decorated function

        Usage:
            @telemetry.track(dimensions={"Service": "CloudFormation"})
            def deploy_template(template_path):
                # Function implementation
        """

        def decorator(func: T) -> T:
            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                op_name = operation or func.__name__
                ns = namespace or self.default_namespace
                dims = {**self.command_dimensions, **(dimensions or {})}

                # Start timing
                start_time = time.perf_counter()
                success = True

                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as e:
                    success = False
                    error_type = self._categorize_error(e)
                    error_metric = self._create_metric(ns)

                    for dim_name, dim_value in dims.items():
                        self._add_dimension(error_metric, dim_name, dim_value)

                    self._add_dimension(
                        error_metric, "InvocationId", self.invocation_id
                    )
                    self._add_dimension(error_metric, "ErrorCategory", error_type)
                    self._add_dimension(error_metric, "ErrorType", type(e).__name__)

                    self._add_metric(
                        error_metric, f"{op_name}.Error", MetricUnit.Count, 1
                    )
                    self._send_metric(error_metric)
                    raise
                finally:
                    # Calculate duration
                    duration_ms = (time.perf_counter() - start_time) * 1000

                    # Create metric
                    metric = self._create_metric(ns)

                    # Add standard dimensions
                    for dim_name, dim_value in dims.items():
                        self._add_dimension(metric, dim_name, dim_value)

                    # Add invocation ID for correlation
                    self._add_dimension(metric, "InvocationId", self.invocation_id)

                    # Add execution metrics
                    self._add_metric(
                        metric,
                        f"{op_name}.Duration",
                        MetricUnit.Milliseconds,
                        duration_ms,
                    )
                    self._add_metric(
                        metric, f"{op_name}.Invocation", MetricUnit.Count, 1
                    )
                    self._add_metric(
                        metric,
                        f"{op_name}.Success",
                        MetricUnit.Count,
                        1 if success else 0,
                    )
                    self._send_metric(metric)

            return cast(T, wrapper)

        return decorator

    def set_command_context(
        self,
        command: str,
        subcommand: Optional[str] = None,
        region: Optional[str] = None,
        profile: Optional[str] = None,
        flags: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Set context for the current CLI command.

        Args:
            command: Primary command name
            subcommand: Subcommand name
            region: AWS region
            profile: AWS profile
            flags: Command flags/options

        This should be called at the beginning of command execution
        to provide context for all subsequent metrics.
        """
        self.command_name = command
        self.subcommand_name = subcommand

        # Build common dimensions
        dimensions = {"Command": command}

        if subcommand:
            dimensions["Subcommand"] = subcommand

        if region:
            dimensions["Region"] = region

        if profile:
            dimensions["Profile"] = profile

        # Add selected important flags if provided
        if flags:
            # Add specific flags that are useful for metrics
            # Filter to just the boolean/string/numeric flags that are useful
            for flag_name, flag_value in flags.items():
                # Only include certain flag types and names
                if isinstance(
                    flag_value, (bool, str, int, float)
                ) and not flag_name.startswith("_"):
                    # Convert flag_name from snake_case to PascalCase for dimensions
                    dim_name = "".join(
                        word.capitalize() for word in flag_name.split("_")
                    )
                    dimensions[f"Flag{dim_name}"] = str(flag_value)

        # Store for later use
        self.command_dimensions = dimensions

        # Send a command start metric
        self.count("CommandStart", dimensions=dimensions)

    def count(
        self,
        name: str,
        value: int = 1,
        dimensions: Optional[Dict[str, str]] = None,
        namespace: Optional[str] = None,
    ) -> None:
        """
        Record a count metric.

        Args:
            name: Metric name
            value: Count value
            dimensions: Additional dimensions
            namespace: Custom namespace

        Usage:
            telemetry.count("ResourcesCreated", 5, dimensions={"Type": "CloudFormation"})
        """
        ns = namespace or self.default_namespace
        dims = {**self.command_dimensions, **(dimensions or {})}

        # Create and send metric
        metric = self._create_metric(ns)

        # Add dimensions
        for dim_name, dim_value in dims.items():
            self._add_dimension(metric, dim_name, dim_value)

        # Add invocation ID
        self._add_dimension(metric, "InvocationId", self.invocation_id)

        # Add the metric
        self._add_metric(metric, name, MetricUnit.Count, value)

        # Send immediately
        self._send_metric(metric)

    def timing(
        self,
        name: str,
        duration_ms: float,
        dimensions: Optional[Dict[str, str]] = None,
        namespace: Optional[str] = None,
    ) -> None:
        """
        Record a timing metric.

        Args:
            name: Metric name
            duration_ms: Duration in milliseconds
            dimensions: Additional dimensions
            namespace: Custom namespace

        Usage:
            # Manually record timing of an operation
            start = time.perf_counter()
            # ... operation ...
            duration_ms = (time.perf_counter() - start) * 1000
            telemetry.timing("TemplateProcessing", duration_ms)
        """
        ns = namespace or self.default_namespace
        dims = {**self.command_dimensions, **(dimensions or {})}

        # Create and send metric
        metric = self._create_metric(ns)

        # Add dimensions
        for dim_name, dim_value in dims.items():
            self._add_dimension(metric, dim_name, dim_value)

        # Add invocation ID
        self._add_dimension(metric, "InvocationId", self.invocation_id)

        # Add the metric
        self._add_metric(metric, name, MetricUnit.Milliseconds, duration_ms)

        # Send immediately
        self._send_metric(metric)

    @contextmanager
    def timer(
        self,
        name: str,
        dimensions: Optional[Dict[str, str]] = None,
        namespace: Optional[str] = None,
    ) -> Generator[None, Any, None]:
        """
        Context manager for timing operations.

        Args:
            name: Metric name
            dimensions: Additional dimensions
            namespace: Custom namespace

        Usage:
            with telemetry.timer("ProcessData", dimensions={"Format": "JSON"}):
                # Code to time
                process_data()
        """
        start_time = time.perf_counter()
        try:
            yield
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self.timing(name, duration_ms, dimensions, namespace)

    def record_command_result(
        self,
        success: bool,
        error: Optional[BaseException] = None,
        duration_ms: Optional[float] = None,
    ) -> None:
        """
        Record the final result of a command execution.

        Args:
            success: Whether the command succeeded
            error: Exception if the command failed
            duration_ms: Command duration if known

        This should be called at the end of command execution to
        record the final status and duration.
        """
        if not self.command_name:
            return  # No command context set

        # Create the metric
        metric = self._create_metric(f"{self.default_namespace}/Commands")

        # Add command dimensions
        for dim_name, dim_value in self.command_dimensions.items():
            self._add_dimension(metric, dim_name, dim_value)

        # Add invocation ID
        self._add_dimension(metric, "InvocationId", self.invocation_id)

        # Add success/failure metrics
        self._add_metric(
            metric, "CommandSuccess", MetricUnit.Count, 1 if success else 0
        )
        self._add_metric(
            metric, "CommandFailure", MetricUnit.Count, 0 if success else 1
        )

        # Add duration if provided
        if duration_ms is not None:
            self._add_metric(
                metric, "CommandDuration", MetricUnit.Milliseconds, duration_ms
            )

        # Send the command result metric
        self._send_metric(metric)

        # If error, send additional error metrics
        if not success and error is not None:
            self.record_error(error)

    def record_error(
        self,
        exception: BaseException,
        command: Optional[str] = None,
        subcommand: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        origin: Optional[ErrorOrigin] = None,
        error_type: Optional[ErrorType] = None,
    ) -> None:
        """
        Record detailed error information for triage dashboards.

        This method captures rich error context and sends structured
        metrics that can be used for drill-down analysis.

        Args:
            exception: The exception that occurred
            command: Command name (if not already set in context)
            subcommand: Subcommand name (if not already set in context)
            metadata: Additional error metadata
            error_type: Error Type
            origin: Error Origin

        Usage:
            try:
                # Operation that might fail
            except Exception as e:
                telemetry.record_error(e, metadata={"resource_id": "res-123"})
                raise

        """
        # Capture error context
        error_ctx = ErrorContext.capture(
            exception,
            command=command or self.command_name or "unknown",
            metadata=metadata,
            origin=origin,
            error_type=error_type,
        )

        # Get error origin and type
        origin = error_ctx["error"]["origin"]
        error_type = error_ctx["error"]["error_type"]

        # Create base dimensions
        dimensions = {**self.command_dimensions}
        if command and "Command" not in dimensions:
            dimensions["Command"] = command
        if subcommand and "Subcommand" not in dimensions:
            dimensions["Subcommand"] = subcommand

        # Level 1: Record overall error count
        self.count(
            "Error",
            1,
            dimensions=dimensions,
            namespace=f"{self.default_namespace}/Errors",
        )

        # Level 2: Record error by origin
        origin_dimensions = {**dimensions, "ErrorOrigin": origin}
        sanitized_origin_dims = self._sanitize_dimensions(origin_dimensions)
        self.count(
            f"Error.{origin}",
            1,
            dimensions=sanitized_origin_dims,
            namespace=f"{self.default_namespace}/Errors/Origin",
        )

        # Level 3: Record error by specific type
        type_dimensions = {
            **origin_dimensions,
            "ErrorType": error_type,
            "ExceptionType": type(exception).__name__,
        }
        sanitized_type_dims = self._sanitize_dimensions(type_dimensions)
        self.count(
            f"Error.{origin}.{error_type}",
            1,
            dimensions=sanitized_type_dims,
            namespace=f"{self.default_namespace}/Errors/Type",
        )

        # Log the full error context as a structured log
        self.logger.error(
            f"Command error: {type(exception).__name__}: {str(exception)}",
            extra={"error_context": error_ctx},
        )

    @staticmethod
    def _create_metric(namespace: str) -> Dict[str, Any]:
        """Create CloudWatch EMF metric structure."""
        return {
            "_aws": {
                "Timestamp": int(datetime.now().timestamp() * 1000),
                "CloudWatchMetrics": [
                    {"Namespace": namespace, "Dimensions": [[]], "Metrics": []}
                ],
            },
            "Dimensions": {},
            "Values": {},
        }

    @staticmethod
    def _add_dimension(metric: Dict[str, Any], name: str, value: str) -> None:
        """Add dimension to EMF metric."""
        if name not in metric["Dimensions"]:
            metric["Dimensions"][name] = str(value)
            dimensions = metric["_aws"]["CloudWatchMetrics"][0]["Dimensions"]
            if [name] not in dimensions:
                dimensions.append([name])

    @staticmethod
    def _add_metric(
        metric: Dict[str, Any],
        name: str,
        unit: Union[str, MetricUnit],
        value: Union[int, float],
    ) -> None:
        """Add metric value to EMF structure."""
        metric["Values"][name] = value

        metrics = metric["_aws"]["CloudWatchMetrics"][0]["Metrics"]
        unit_value = unit if isinstance(unit, str) else unit.value

        if not any(m.get("Name") == name for m in metrics):
            metrics.append({"Name": name, "Unit": unit_value})

    def _send_metric(self, metric: Dict[str, Any]) -> None:
        """Send a metric via the logger."""
        # Extract useful information from the metric for display
        namespace = metric["_aws"]["CloudWatchMetrics"][0]["Namespace"]

        # Get metrics with their values
        metrics_with_values = []
        for m in metric["_aws"]["CloudWatchMetrics"][0]["Metrics"]:
            metric_name = m["Name"]
            metric_value = metric["Values"].get(metric_name, "N/A")
            metrics_with_values.append(f"{metric_name}={metric_value}")

        # Format dimensions as key=value pairs
        dimensions = [f"{k}={v}" for k, v in metric["Dimensions"].items()]
        dim_str = ", ".join(dimensions) if dimensions else "none"

        # Create a more informative message
        message = (
            f"METRIC: {namespace} - Metrics: {', '.join(metrics_with_values)} "
            f"- Dimensions: {dim_str}"
        )

        # Log with the descriptive message and still include the full data in extra
        self.logger.info(message, extra={"metric_data": metric})

    def _sanitize_dimensions(self, dimensions: Dict[str, Any]) -> Dict[str, str]:
        """Filter out None values and convert all values to strings."""
        return {k: str(v) for k, v in dimensions.items() if v is not None}

    @staticmethod
    def _categorize_error(exception: Exception) -> str:
        """Categorize an exception for better error metrics."""
        error_ctx = ErrorContext.capture(exception)
        return f"{error_ctx['error']['origin']}.{error_ctx['error']['error_type']}"
