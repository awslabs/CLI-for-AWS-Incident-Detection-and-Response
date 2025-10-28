import logging
from typing import Optional

from injector import Injector, Module, provider, singleton

from aws_idr_customer_cli.utils.log_formatter import ColoredFormatter
from aws_idr_customer_cli.utils.log_handlers import CliLogger

LOG_LEVEL = logging.INFO


class LoggingModule(Module):
    def __init__(self) -> None:
        self._console_handler: Optional[logging.StreamHandler] = None

    @singleton
    @provider
    def provide_logger(self) -> CliLogger:
        # Create logger with built-in buffer handler, no console output by default
        logger = CliLogger("idr_cli", level=LOG_LEVEL)
        return logger

    def enable_console_logging(self, logger: CliLogger, level: int) -> None:
        """Enable console logging at the specified level."""
        # Remove existing console handler if present
        if self._console_handler:
            logger.removeHandler(self._console_handler)

        # Add new console handler with specified level
        self._console_handler = logging.StreamHandler()
        formatter = ColoredFormatter("%(asctime)s [%(levelname)s] %(message)s")
        self._console_handler.setFormatter(formatter)
        self._console_handler.setLevel(level)
        logger.addHandler(self._console_handler)

        # Also update the logger's own level to ensure messages get through
        logger.setLevel(min(logger.level, level))

    @staticmethod
    def configure_console_logging(
        injector: Injector,
        verbose: bool = False,
        debug: bool = False,
        logger: Optional[CliLogger] = None,
    ) -> None:
        """
        Configure console logging based on verbose and debug flags.

        Args:
            injector: Dependency injector to get LoggingModule and CliLogger
            verbose: Enable verbose (INFO level) logging
            debug: Enable debug (DEBUG level) logging
            logger: Optional logger instance. If None, gets from injector
        """
        # Only configure if flags are set
        if not verbose and not debug:
            return

        logging_module = injector.get(LoggingModule)

        # Use provided logger or get from injector
        if logger is None:
            logger = injector.get(CliLogger)

        # Configure logging level based on flags
        if debug:
            logging_module.enable_console_logging(logger, logging.DEBUG)
        elif verbose:
            logging_module.enable_console_logging(logger, logging.INFO)
        # If neither flag is set, no console logging (default)
