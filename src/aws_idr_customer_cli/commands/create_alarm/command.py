import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional, cast

import click
from injector import inject

from aws_idr_customer_cli.clients.iam import BotoIamManager
from aws_idr_customer_cli.clients.sts import BotoStsManager
from aws_idr_customer_cli.commands.register_workload.command import RegisterWorkload
from aws_idr_customer_cli.core.command_base import CommandBase
from aws_idr_customer_cli.core.decorators import command, option
from aws_idr_customer_cli.core.interactive.ui import InteractiveUI
from aws_idr_customer_cli.input.input_resource_discovery import InputResourceDiscovery
from aws_idr_customer_cli.services.create_alarm.alarm_recommendation_service import (
    AlarmRecommendationService,
)
from aws_idr_customer_cli.services.create_alarm.alarm_service import AlarmService
from aws_idr_customer_cli.services.file_cache.data import OnboardingSubmission
from aws_idr_customer_cli.services.file_cache.file_cache_service import FileCacheService
from aws_idr_customer_cli.services.non_interactive_alarm_service import (
    NonInteractiveAlarmService,
)
from aws_idr_customer_cli.services.support_case_service import (
    SupportCaseService,
)
from aws_idr_customer_cli.utils.context import set_integration_test_mode
from aws_idr_customer_cli.utils.execution_mode import ExecutionMode, set_execution_mode
from aws_idr_customer_cli.utils.log_handlers import CliLogger
from aws_idr_customer_cli.utils.session.alarm_creation_session import (
    AlarmCreationSession,
)
from aws_idr_customer_cli.utils.session.session_store import SessionStore


@command("create-alarms")
class CreateAlarm(CommandBase):
    """Create recommended CloudWatch alarms.

    Examples:

    \b
        awsidr create-alarms
        awsidr create-alarms --resume {sessionId}
        awsidr create-alarms -ma True
        awsidr create-alarms --verbose
        awsidr create-alarms --debug
    """

    @inject
    def __init__(
        self,
        alarm_service: AlarmService,
        logger: CliLogger,
        store: SessionStore,
        sts_manager: BotoStsManager,
        iam_manager: BotoIamManager,
        file_cache_service: FileCacheService,
        input_resource_discovery: InputResourceDiscovery,
        alarm_recommendation_service: AlarmRecommendationService,
        support_case_service: SupportCaseService,
        ui: InteractiveUI,
        non_interactive_alarm_service: NonInteractiveAlarmService,
    ) -> None:
        self.alarm_service = alarm_service
        self.logger = logger
        self.store = store
        self._sts_manager = sts_manager
        self._iam_manager = iam_manager
        self.file_cache_service = file_cache_service
        self.input_resource_discovery = input_resource_discovery
        self.alarm_recommendation_service = alarm_recommendation_service
        self.support_case_service = support_case_service
        self.ui = ui
        self._non_interactive_alarm_service = non_interactive_alarm_service
        self._account_id: Optional[str] = None

    def _display_workload_summary(self, submission: OnboardingSubmission) -> None:
        """Display workload information summary."""
        now = datetime.now(timezone.utc)
        created_ago = self._format_time_delta(now - submission.created_at)
        updated_ago = self._format_time_delta(now - submission.last_updated_at)

        workload = submission.workload_onboard

        self.ui.display_result(
            "🏢 Workload Details",
            {
                "Name": workload.name or "(not set)",
                "Regions": (
                    ", ".join(workload.regions) if workload.regions else "(not set)"
                ),
                "Created": f"{submission.created_at.strftime('%Y-%m-%d %H:%M')} "
                f"({created_ago} ago)",
                "Last Updated": f"{submission.last_updated_at.strftime('%Y-%m-%d %H:%M')} "
                f"({updated_ago} ago)",
            },
        )

    def _display_progress_status(self, submission: OnboardingSubmission) -> None:
        """Display progress status using new progress tracking structure."""

        # Prioritize alarm creation progress if it exists
        if submission.progress.alarm_creation:
            alarm_tracker = submission.progress.alarm_creation
            step_descriptions = AlarmCreationSession.get_step_names()
            current_step = alarm_tracker.current_step
            total_steps = len(step_descriptions)

            if current_step >= total_steps:
                self.ui.display_info("✅ Alarm creation completed!", style="green")

                if step_descriptions:
                    final_step = step_descriptions[-1]
                    self.ui.display_info(
                        f"✅ Final Step Completed: {final_step}", style="dim"
                    )
            else:
                # Show current alarm creation progress
                progress_bar = "█" * current_step + "░" * (total_steps - current_step)
                self.ui.display_info(
                    f"🔄 Alarm Creation Progress: {progress_bar} ({current_step}/{total_steps})",
                    style="blue",
                )

                if current_step > 0:
                    last_completed_step = step_descriptions[current_step - 1]
                    self.ui.display_info(
                        f"✅ Last Completed: {last_completed_step}", style="dim"
                    )

                if current_step < len(step_descriptions):
                    next_step_name = step_descriptions[current_step]
                    self.ui.display_info(
                        f"🎯 Next Step: {next_step_name}", style="green"
                    )

            # Show recently completed alarm steps
            if alarm_tracker.completed_steps:
                recent_completed = ", ".join(alarm_tracker.completed_steps[-2:])
                self.ui.display_info(
                    f"📋 Recently Completed: {recent_completed}", style="dim"
                )
            return

        RegisterWorkload.display_session_progress_status(
            ui=self.ui, submission=submission
        )

    def _prompt_resume(self, submission: OnboardingSubmission) -> bool:
        """Enhanced prompt with full session context for informed decision."""

        self.ui.display_header(
            "Found Existing Alarm Session",
            "Review the details below to decide whether to continue or start fresh:",
        )

        if submission.workload_onboard:
            self._display_workload_summary(submission)

        self._display_progress_status(submission=submission)

        self.ui.display_info("\n📋 Your Options:", style="blue")
        self.ui.display_info("  • Continue: Resume from where you left off")
        self.ui.display_info("  • Start Fresh: Begin a new alarm creation session")

        return cast(
            bool,
            self.ui.prompt_confirm("Continue with existing session?", default=True),
        )

    @staticmethod
    def _format_time_delta(delta: Any) -> str:
        """Format timedelta as human-readable string."""
        total_seconds = int(delta.total_seconds())

        if total_seconds < 60:
            return f"{total_seconds} second(s)"
        elif total_seconds < 3600:
            minutes = total_seconds // 60
            return f"{minutes} minute(s)"
        elif total_seconds < 86400:
            hours = total_seconds // 3600
            return f"{hours} hour(s)"
        else:
            days = total_seconds // 86400
            return f"{days} day(s)"

    def _find_latest_workload_session_id(self) -> Optional[str]:
        """Find the latest submission with completed workload_onboarding."""
        try:
            existing = self.store.find_latest_for_account(self._account_id)
            if not existing:
                return None

            session_id, submission = existing

            # Check if alarm creation is in progress
            if submission.progress.alarm_creation:
                return str(session_id)

            # Check workload onboarding status
            workload = submission.workload_onboard
            if not workload:
                return None

            if workload.support_case_id:
                self.ui.display_info("Loading previous onboarding data...")
                return str(session_id)

            # Workload exists but incomplete
            self.ui.display_warning(
                "⚠️  Workload Registration Incomplete\n\n"
                "Your workload registration is still in progress and has not completed.\n\n"
                "To continue the registration process, please run:\n"
                "    awsidr register-workload\n"
            )
            return None

        except Exception as e:
            self.logger.error(
                f"Error finding latest workload session for account {self._account_id}: {e}"
            )
            return None

    def _create_alarm_session(
        self, resume_session_id: Optional[str] = None
    ) -> AlarmCreationSession:
        """Create alarm creation session."""
        return AlarmCreationSession(
            store=self.store,
            alarm_service=self.alarm_service,
            file_cache_service=self.file_cache_service,
            input_resource_discovery=self.input_resource_discovery,
            alarm_recommendation_service=self.alarm_recommendation_service,
            account_id=self._account_id,
            resume_session_id=resume_session_id,
            support_case_service=self.support_case_service,
            iam_manager=self._iam_manager,
        )

    def _execute_from_config(
        self, config_path: str, mock_account_id: bool
    ) -> Dict[str, Any]:
        """Execute alarm creation from config file."""
        with open(config_path, "r") as f:
            config = json.load(f)

        account_id = (
            "123456789012"
            if mock_account_id
            else self._sts_manager.retrieve_account_id_from_sts()
        )

        self._non_interactive_alarm_service.create_alarms_from_config(
            config, account_id
        )

        return {}

    def _execute_business_logic(
        self, mock_account_id: bool, resume: Optional[str] = None, **kwargs: Any
    ) -> Dict[str, Any]:
        """Execute alarm creation business logic."""
        self._account_id = (
            "123456789012"
            if mock_account_id
            else self._sts_manager.retrieve_account_id_from_sts()
        )

        if resume:
            session = self._create_alarm_session(resume_session_id=resume)
            result = session.execute()
            return cast(Dict[str, Any], result)

        # Check for existing session and display details
        existing = self.store.find_latest_alarm_ready_session(self._account_id)
        if existing:
            session_id, submission = existing
            # Prompt user to resume or start fresh
            if self._prompt_resume(submission=submission):
                session = self._create_alarm_session(resume_session_id=session_id)
                result = session.execute()
                return cast(Dict[str, Any], result)
            else:
                # User chose to start fresh
                session = self._create_alarm_session(resume_session_id=None)
                result = session.execute()
                return cast(Dict[str, Any], result)
        else:
            self.ui.display_warning(
                "We couldn't find any workloads created through this tool "
                "that are ready for alarm creation \n"
            )
            if self.ui.prompt_confirm(
                "Proceed with alarm creation for pre-existing workloads?",
                default=True,
            ):
                session = self._create_alarm_session(resume_session_id=None)
                result = session.execute()
                return cast(Dict[str, Any], result)
            else:
                self.ui.display_info(
                    "Please execute: awsidr register-workload. \n" "Exiting ..."
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
    @option(
        "--config",
        help="Path to JSON configuration file",
    )
    def execute(
        self,
        mock_account_id: bool,
        resume: Optional[str] = None,
        test_mode: bool = False,
        config: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Execute alarm creation"""
        try:
            set_integration_test_mode(test_mode)
            if config:
                set_execution_mode(ExecutionMode.NON_INTERACTIVE)
                return self._execute_from_config(config, mock_account_id)

            set_execution_mode(ExecutionMode.INTERACTIVE)
            return self._execute_business_logic(mock_account_id, resume, **kwargs)
        except Exception as e:
            self.logger.error(f"Failed: {e}")
            raise click.ClickException(str(e))
