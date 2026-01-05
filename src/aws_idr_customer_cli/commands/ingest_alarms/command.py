import json
from typing import Any, Dict, Optional, cast

import click
from injector import inject

from aws_idr_customer_cli.clients.iam import BotoIamManager
from aws_idr_customer_cli.clients.sts import BotoStsManager
from aws_idr_customer_cli.core.command_base import CommandBase
from aws_idr_customer_cli.core.decorators import command, option
from aws_idr_customer_cli.core.interactive.ui import InteractiveUI
from aws_idr_customer_cli.data_accessors.eventbridge_accessor import (
    EventBridgeAccessor,
)
from aws_idr_customer_cli.input.input_resource_discovery import InputResourceDiscovery
from aws_idr_customer_cli.services.create_alarm.alarm_service import AlarmService
from aws_idr_customer_cli.services.file_cache.data import OnboardingSubmission
from aws_idr_customer_cli.services.non_interactive_alarm_ingestion_service import (
    NonInteractiveAlarmIngestionService,
)
from aws_idr_customer_cli.services.support_case_service import SupportCaseService
from aws_idr_customer_cli.utils.constants import MOCK_ACCOUNT_ID
from aws_idr_customer_cli.utils.context import set_integration_test_mode
from aws_idr_customer_cli.utils.execution_mode import ExecutionMode, set_execution_mode
from aws_idr_customer_cli.utils.log_handlers import CliLogger
from aws_idr_customer_cli.utils.session.alarm_ingestion_session import (
    AlarmIngestionSession,
)
from aws_idr_customer_cli.utils.session.session_store import SessionStore
from aws_idr_customer_cli.utils.validate_alarm.alarm_validator import (
    AlarmValidator,
)
from aws_idr_customer_cli.utils.validation.validator import Validate


@command("ingest-alarms")
class IngestAlarms(CommandBase):
    """Ingest existing CloudWatch alarms into IDR for monitoring."""

    @inject
    def __init__(
        self,
        logger: CliLogger,
        store: SessionStore,
        sts_manager: BotoStsManager,
        iam_manager: BotoIamManager,
        input_resource_discovery: InputResourceDiscovery,
        validator: Validate,
        alarm_validator: AlarmValidator,
        alarm_service: AlarmService,
        support_case_service: SupportCaseService,
        ui: InteractiveUI,
        non_interactive_alarm_ingestion_service: NonInteractiveAlarmIngestionService,
        eventbridge_accessor: EventBridgeAccessor,
    ) -> None:
        super().__init__()
        self.logger = logger
        self.store = store
        self._sts_manager = sts_manager
        self._iam_manager = iam_manager
        self.input_resource_discovery = input_resource_discovery
        self.validator = validator
        self.alarm_validator = alarm_validator
        self.alarm_service = alarm_service
        self.support_case_service = support_case_service
        self.ui = ui
        self._non_interactive_alarm_ingestion_service = (
            non_interactive_alarm_ingestion_service
        )
        self.eventbridge_accessor = eventbridge_accessor
        self._account_id: Optional[str] = None

    def _create_alarm_ingestion_session(
        self, resume_session_id: Optional[str] = None
    ) -> AlarmIngestionSession:
        return AlarmIngestionSession(
            store=self.store,
            input_resource_discovery=self.input_resource_discovery,
            validator=self.validator,
            comprehensive_validator=self.alarm_validator,
            support_case_service=self.support_case_service,
            iam_manager=self._iam_manager,
            alarm_service=self.alarm_service,
            eventbridge_accessor=self.eventbridge_accessor,
            account_id=self._account_id,
            resume_session_id=resume_session_id,
        )

    def _execute_from_config(
        self, config_path: str, mock_account_id: bool
    ) -> Dict[str, Any]:
        """Execute alarm ingestion from config file."""
        with open(config_path, "r") as f:
            config = json.load(f)

        account_id = (
            MOCK_ACCOUNT_ID
            if mock_account_id
            else self._sts_manager.retrieve_account_id_from_sts()
        )

        self._non_interactive_alarm_ingestion_service.ingest_alarms_from_config(
            config=config, account_id=account_id
        )

        return {}

    def _execute_business_logic(
        self,
        mock_account_id: bool,
        resume: Optional[str] = None,
        test_mode: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        self._account_id = (
            MOCK_ACCOUNT_ID
            if mock_account_id
            else self._sts_manager.retrieve_account_id_from_sts()
        )

        # Pass test_mode to support_case_service
        self.support_case_service.test_mode = test_mode

        if resume:
            session = self._create_alarm_ingestion_session(resume_session_id=resume)
            return cast(Dict[str, Any], session.execute())

        # Check for existing alarm ingestion session
        existing = self.store.find_latest_alarm_ingestion_session(self._account_id)
        if existing:
            session_id, submission = existing
            # Prompt user to resume or start fresh
            if self._prompt_resume(submission=submission):
                session = self._create_alarm_ingestion_session(
                    resume_session_id=session_id
                )
                return cast(Dict[str, Any], session.execute())
            else:
                # User chose to start fresh
                session = self._create_alarm_ingestion_session(resume_session_id=None)
                return cast(Dict[str, Any], session.execute())
        else:
            # No existing session, start fresh
            session = self._create_alarm_ingestion_session(resume_session_id=None)
            return cast(Dict[str, Any], session.execute())

    def _prompt_resume(self, submission: OnboardingSubmission) -> bool:
        self.ui.display_header(
            "Found Existing Alarm Ingestion Session",
            "Review the details below to decide whether to continue or start fresh:",
        )

        if submission.workload_onboard:
            self._display_workload_summary(submission)

        self._display_progress_status(submission=submission)

        self.ui.display_info("\n📋 Your Options:", style="blue")
        self.ui.display_info("  • Continue: Resume from where you left off")
        self.ui.display_info("  • Start Fresh: Begin a new alarm ingestion session")

        return cast(
            bool,
            self.ui.prompt_confirm("Continue with existing session?", default=True),
        )

    def _display_workload_summary(self, submission: OnboardingSubmission) -> None:
        if not submission.workload_onboard:
            return

        workload = submission.workload_onboard
        self.ui.display_info(f"\n🏢 Workload: {workload.name}")
        self.ui.display_info(f"🌍 Regions: {', '.join(workload.regions)}")

    def _display_progress_status(self, submission: OnboardingSubmission) -> None:
        if submission.progress.alarm_ingestion:
            progress = submission.progress.alarm_ingestion
            self.ui.display_info(
                f"\n📊 Progress: Step {progress.current_step}/{progress.total_steps}"
            )
            if progress.step_name:
                self.ui.display_info(f"📍 Current Step: {progress.step_name}")
        else:
            self.ui.display_info("\n📊 Progress: Ready to start alarm ingestion")

    @option("--resume", "-r", help="Resume session ID")
    @option(
        "--mock-account-id",
        "-ma",
        default=False,
        help="Test option to bypass sts boto call.",
    )
    @option("--test-mode", is_flag=True, hidden=True)
    @option(
        "--config",
        help="Path to JSON configuration file",
    )
    def execute(
        self,
        mock_account_id: bool = False,
        resume: Optional[str] = None,
        test_mode: bool = False,
        config: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        try:
            set_integration_test_mode(test_mode)

            if config:
                set_execution_mode(ExecutionMode.NON_INTERACTIVE)
                self._execute_from_config(config, mock_account_id)
                return

            set_execution_mode(ExecutionMode.INTERACTIVE)
            self._execute_business_logic(mock_account_id, resume, test_mode, **kwargs)
        except Exception as e:
            self.logger.error(f"Failed: {e}")
            raise click.ClickException(str(e))
