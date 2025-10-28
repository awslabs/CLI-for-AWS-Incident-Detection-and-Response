from __future__ import annotations

import json
import logging
from datetime import datetime
from logging import Logger
from typing import Any, Dict, List, Tuple

from aws_idr_customer_cli.utils.log_formatter import ColoredFormatter


class BufferingHandler(logging.Handler):
    """Handler that buffers logs for CloudWatch and local summaries."""

    def __init__(self, capacity: int = 1000):
        super().__init__()
        self.buffer: List[logging.LogRecord] = []
        self.capacity = capacity

    def emit(self, record: logging.LogRecord) -> None:
        """Store the log record in buffer."""
        self.buffer.append(record)
        if len(self.buffer) > self.capacity:
            self.buffer.pop(0)

    def get_logs(self) -> List[str]:
        """Get all buffered logs as formatted strings."""
        return [self.format(record) for record in self.buffer]

    def clear(self) -> None:
        """Clear the buffer."""
        self.buffer.clear()

    def get_summary(self) -> Dict[str, int]:
        """Get summary of log levels."""
        summary = {"DEBUG": 0, "INFO": 0, "WARNING": 0, "ERROR": 0, "CRITICAL": 0}

        for record in self.buffer:
            level_name = record.levelname
            if level_name in summary:
                summary[level_name] += 1

        return summary

    def print_summary(self, logger: "CliLogger") -> None:
        """Print summary using the provided logger."""
        summary = self.get_summary()
        total_count = sum(summary.values())

        logger.info("=" * 50)
        logger.info(f"EXECUTION SUMMARY (Total logs: {total_count})")
        logger.info("=" * 50)

        for level, count in summary.items():
            if count > 0:
                logger.info(f"{level}: {count}")

    def format_exception(self, exc_info: Tuple) -> str:
        """Format exception info into a string."""
        if self.formatter:
            return self.formatter.formatException(exc_info)
        else:
            import traceback

            return "\n".join(traceback.format_exception(*exc_info))

    def get_cloudwatch_logs(self) -> List[Dict[str, Any]]:
        """Format logs for CloudWatch Logs Insights queries."""
        cloudwatch_logs = []

        for record in self.buffer:
            cloudwatch_logs.append(self.get_cloudwatch_format(record))

        return cloudwatch_logs

    def get_cloudwatch_format(self, record: logging.LogRecord) -> Dict[str, Any]:
        """Format a single log record for CloudWatch Insights."""
        log_entry = {
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "function": record.funcName,
            "line": record.lineno,
            "module": record.module,
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
        }

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.format_exception(record.exc_info)

        # Add any custom attributes from record.__dict__
        # that might have been added with extra parameter
        for key, value in record.__dict__.items():
            # Skip standard attributes and objects that can't be serialized to JSON
            if (
                key not in log_entry
                and key
                not in (
                    "args",
                    "exc_info",
                    "exc_text",
                    "stack_info",
                    "lineno",
                    "funcName",
                    "created",
                    "msecs",
                    "pathname",
                    "levelno",
                )
                and isinstance(value, (str, int, float, bool, list, dict, tuple))
            ):
                log_entry[key] = value

        return log_entry

    def get_json_logs(self) -> str:
        """Get all logs as a single JSON string."""
        return json.dumps(self.get_cloudwatch_logs())

    def save_logs_to_file(self, filename: str) -> bool:
        """Save logs to a local file."""
        try:
            with open(filename, "w") as f:
                json.dump(self.get_cloudwatch_logs(), f, indent=2)
            return True
        except Exception:
            return False


class CliLogger(Logger):
    def __init__(self, name: str, level: int = logging.NOTSET) -> None:
        super().__init__(name, level)
        # Initialize buffer handler
        self._buffer_handler = BufferingHandler(capacity=1000)
        formatter = ColoredFormatter("%(asctime)s [%(levelname)s] %(message)s")
        self._buffer_handler.setFormatter(formatter)
        # Add buffer handler to the logger
        self.addHandler(self._buffer_handler)

    @property
    def buffer_handler(self) -> BufferingHandler:
        return self._buffer_handler
