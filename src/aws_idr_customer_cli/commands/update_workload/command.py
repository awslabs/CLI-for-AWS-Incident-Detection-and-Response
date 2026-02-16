import json
from typing import Any, Dict, Optional

import click
from injector import inject

from aws_idr_customer_cli.clients.sts import BotoStsManager
from aws_idr_customer_cli.core.command_base import CommandBase
from aws_idr_customer_cli.core.decorators import command, option
from aws_idr_customer_cli.core.interactive.ui import InteractiveUI
from aws_idr_customer_cli.input.input_resource_discovery import InputResourceDiscovery
from aws_idr_customer_cli.services.non_interactive_workload_update_service import (
    NonInteractiveWorkloadUpdateService,
)
from aws_idr_customer_cli.services.support_case_service import SupportCaseService
from aws_idr_customer_cli.utils.constants import MOCK_ACCOUNT_ID
from aws_idr_customer_cli.utils.context import set_integration_test_mode
from aws_idr_customer_cli.utils.execution_mode import ExecutionMode, set_execution_mode
from aws_idr_customer_cli.utils.log_handlers import CliLogger
from aws_idr_customer_cli.utils.session.session_store import SessionStore
from aws_idr_customer_cli.utils.session.update_session import UpdateSession
from aws_idr_customer_cli.utils.validation.validator import Validate


@command("update-workload")
class UpdateWorkload(CommandBase):
    """Request updates to an existing IDR workload.

    Examples:

    \b
        awsidr update-workload
        awsidr update-workload --resume {sessionId}
        awsidr update-workload --config update-config.json
    """

    @inject
    def __init__(
        self,
        logger: CliLogger,
        ui: InteractiveUI,
        store: SessionStore,
        sts_manager: BotoStsManager,
        support_case_service: SupportCaseService,
        validator: Validate,
        input_resource_discovery: InputResourceDiscovery,
        non_interactive_service: NonInteractiveWorkloadUpdateService,
    ) -> None:
        super().__init__()
        self.logger = logger
        self.ui = ui
        self.store = store
        self._sts_manager = sts_manager
        self._support_case_service = support_case_service
        self._validator = validator
        self._input_resource_discovery = input_resource_discovery
        self._non_interactive_service = non_interactive_service

    def _create_session(
        self,
        account_id: str,
        resume_session_id: Optional[str] = None,
    ) -> UpdateSession:
        """Create update session."""
        return UpdateSession(
            store=self.store,
            support_case_service=self._support_case_service,
            validator=self._validator,
            input_resource_discovery=self._input_resource_discovery,
            account_id=account_id,
            resume_session_id=resume_session_id,
        )

    def _execute_from_config(
        self, config_path: str, mock_account_id: bool
    ) -> Dict[str, Any]:
        """Execute workload update from config file."""
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
        except json.JSONDecodeError as e:
            raise click.ClickException(f"Invalid JSON in config file: {e}")
        except FileNotFoundError:
            raise click.ClickException(f"Config file not found: {config_path}")

        account_id = (
            MOCK_ACCOUNT_ID
            if mock_account_id
            else self._sts_manager.retrieve_account_id_from_sts()
        )

        self._non_interactive_service.update_workload_from_config(
            config=config, account_id=account_id
        )
        return {}

    @option("--resume", "-r", help="Resume session ID")
    @option(
        "--mock-account-id",
        "-ma",
        default=False,
        help="Test option to bypass sts boto call.",
    )
    @option("--test-mode", is_flag=True, hidden=True)
    @option("--config", help="Path to JSON configuration file for non-interactive mode")
    def execute(
        self,
        resume: Optional[str] = None,
        mock_account_id: bool = False,
        test_mode: bool = False,
        config: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Execute workload update request."""
        try:
            set_integration_test_mode(test_mode)

            if config:
                set_execution_mode(ExecutionMode.NON_INTERACTIVE)
                return self._execute_from_config(config, mock_account_id)

            set_execution_mode(ExecutionMode.INTERACTIVE)
            account_id = (
                MOCK_ACCOUNT_ID
                if mock_account_id
                else self._sts_manager.retrieve_account_id_from_sts()
            )

            session = self._create_session(account_id, resume)
            result: Dict[str, Any] = session.execute()
            result["session_id"] = session.session_id
            return result

        except Exception as e:
            self.logger.error(f"Failed: {e}")
            raise click.ClickException(str(e))

    def output(self, result: Dict[str, Any]) -> None:
        """Handle output."""
        status = result.get("status")

        if status == "completed":
            self.logger.info("✅ Update request submitted successfully")
        elif status == "paused":
            session_id = result.get("session_id")
            self.logger.info(f"Session paused. Resume with: --resume {session_id}")
        elif status == "quit":
            session_id = result.get("session_id")
            self.logger.info(f"Session saved. Resume with: --resume {session_id}")
        elif status == "dry_run":
            self.logger.info("🔍 Dry run completed - no changes made")
