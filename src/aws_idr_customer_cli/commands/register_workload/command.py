import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional, cast

import click
from injector import inject

from aws_idr_customer_cli.clients.iam import BotoIamManager
from aws_idr_customer_cli.clients.sts import BotoStsManager
from aws_idr_customer_cli.core.command_base import CommandBase
from aws_idr_customer_cli.core.decorators import command, option
from aws_idr_customer_cli.core.interactive.ui import InteractiveUI
from aws_idr_customer_cli.input.input_resource_discovery import (
    InputResourceDiscovery,
)
from aws_idr_customer_cli.services.create_alarm.alarm_recommendation_service import (
    AlarmRecommendationService,
)
from aws_idr_customer_cli.services.create_alarm.alarm_service import AlarmService
from aws_idr_customer_cli.services.file_cache.data import OnboardingSubmission
from aws_idr_customer_cli.services.file_cache.file_cache_service import FileCacheService
from aws_idr_customer_cli.services.non_interactive_workload_service import (
    NonInteractiveWorkloadService,
)
from aws_idr_customer_cli.services.support_case_service import SupportCaseService
from aws_idr_customer_cli.utils.context import set_integration_test_mode
from aws_idr_customer_cli.utils.execution_mode import ExecutionMode, set_execution_mode
from aws_idr_customer_cli.utils.log_handlers import CliLogger
from aws_idr_customer_cli.utils.session.alarm_creation_session import (
    AlarmCreationSession,
)
from aws_idr_customer_cli.utils.session.session_store import SessionStore
from aws_idr_customer_cli.utils.session.workload_session import WorkloadSession
from aws_idr_customer_cli.utils.validation.validator import Validate


@command("register-workload")
class RegisterWorkload(CommandBase):
    """Register workload - collect info only.

    Examples:

    \b
        awsidr register-workload
        awsidr register-workload --resume {sessionId}
        awsidr register-workload -ma True
        awsidr register-workload --verbose
        awsidr register-workload --debug
    """

    def _prompt_resume(self, submission: OnboardingSubmission) -> bool:
        """Enhanced prompt with full session context for informed decision."""

        # Display session header
        self.ui.display_header(
            "Found Existing Workload Session",
            "Review the details below to decide whether to continue or start fresh:",
        )

        # Show workload information if available
        if submission.workload_onboard:
            self._display_workload_summary(submission)

        # Show next steps
        self.display_session_progress_status(ui=self.ui, submission=submission)

        self.ui.display_info("\n📋 Your Options:", style="blue")
        self.ui.display_info("  • Continue: Resume from where you left off")
        self.ui.display_info("  • Start Fresh: Begin a new workload registration")

        return cast(
            bool,
            self.ui.prompt_confirm("Continue with existing session?", default=True),
        )

    def _display_workload_summary(self, submission: OnboardingSubmission) -> None:
        """Display workload information summary."""
        # Calculate time elapsed
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

    @staticmethod
    def display_session_progress_status(
        ui: InteractiveUI, submission: OnboardingSubmission
    ) -> None:
        """Display progress status using new progress tracking structure."""

        workload_tracker = submission.progress.workload_registration

        if not workload_tracker:
            ui.display_info(
                "🎯 Status: Ready to start workload registration", style="green"
            )
            return

        # Get step names dynamically
        step_descriptions = WorkloadSession.get_step_names()

        current_step = workload_tracker.current_step
        total_steps = len(step_descriptions)

        if current_step >= total_steps:
            ui.display_info("✅ Workload registration completed!", style="green")

            # Show final completed step
            if step_descriptions:
                final_step = step_descriptions[-1]  # Last step in the list
                ui.display_info(f"✅ Final Step Completed: {final_step}", style="dim")

            # Check next phase status
            if submission.workload_to_alarm_handoff:
                ui.display_info("🚀 Ready for alarm creation phase", style="blue")
            elif submission.progress.alarm_creation:
                alarm_tracker = submission.progress.alarm_creation
                ui.display_info(
                    f"🔄 Alarm creation: {alarm_tracker.current_step}/"
                    f"{alarm_tracker.total_steps}",
                    style="blue",
                )
        else:
            # Show current progress
            progress_bar = "█" * current_step + "░" * (total_steps - current_step)
            ui.display_info(
                f"📊 Progress: {progress_bar} ({current_step}/{total_steps})",
                style="blue",
            )

            # Show last completed step (if any)
            if current_step > 0:
                last_completed_step = step_descriptions[current_step - 1]
                ui.display_info(
                    f"✅ Last Completed: {last_completed_step}", style="dim"
                )

            # Show next step
            if current_step < len(step_descriptions):
                next_step_name = step_descriptions[current_step]
                ui.display_info(f"🎯 Next Step: {next_step_name}", style="green")

        # Show recently completed steps from tracker (if available)
        if workload_tracker.completed_steps:
            recent_completed = ", ".join(
                workload_tracker.completed_steps[-2:]
            )  # Last 2 steps
            ui.display_info(f"📋 Recently Completed: {recent_completed}", style="dim")

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

    def _create_workload_session(
        self, resume_session_id: Optional[str] = None
    ) -> WorkloadSession:
        """Create a WorkloadSession instance."""
        return WorkloadSession(
            store=self.store,
            account_id=self._account_id,
            resume_session_id=resume_session_id,
            input_resource_discovery=self._input_resource_discovery,
            validator=self._validator,
            support_case_service=self._support_case_service,
        )

    def _create_alarm_session(
        self, resume_session_id: Optional[str] = None
    ) -> AlarmCreationSession:
        """Create alarm creation session."""
        return AlarmCreationSession(
            store=self.store,
            alarm_service=self._alarm_service,
            file_cache_service=self._file_cache_service,
            input_resource_discovery=self._input_resource_discovery,
            alarm_recommendation_service=self._alarm_recommendation_service,
            account_id=self._account_id,
            resume_session_id=resume_session_id,
            support_case_service=self._support_case_service,
            iam_manager=self._iam_manager,
        )

    @inject
    def __init__(
        self,
        logger: CliLogger,
        store: SessionStore,
        sts_manager: BotoStsManager,
        iam_manager: BotoIamManager,
        validator: Validate,
        input_resource_discovery: InputResourceDiscovery,
        support_case_service: SupportCaseService,
        ui: InteractiveUI,
        alarm_service: AlarmService,
        file_cache_service: FileCacheService,
        alarm_recommendation_service: AlarmRecommendationService,
        non_interactive_service: NonInteractiveWorkloadService,
    ) -> None:
        self.logger = logger
        self.store = store
        self._sts_manager = sts_manager
        self._iam_manager = iam_manager
        # hard assumption is cloudshell has AWS_REGION anytime
        self._input_resource_discovery = input_resource_discovery
        self._account_id: Optional[str] = None
        self._validator = validator
        self._support_case_service = support_case_service
        self.ui = ui
        self._alarm_service = alarm_service
        self._file_cache_service = file_cache_service
        self._alarm_recommendation_service = alarm_recommendation_service
        self._non_interactive_service = non_interactive_service

    def _execute_business_logic(
        self,
        mock_account_id: bool,
        resume: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Execute workload info collection business logic."""
        self._account_id = (
            "123456789012"
            if mock_account_id
            else self._sts_manager.retrieve_account_id_from_sts()
        )

        # If resume is provided, skip scanning and go directly to resuming
        if resume:
            session = self._create_workload_session(resume)
            result = session.execute()

            # Check if user chose to proceed to alarm creation
            if result.get("workflow_transition") == "alarm_creation":
                self.logger.info("🚀 Starting alarm creation phase...")
                workload_session_id = result.get("session_id")
                alarm_session = self._create_alarm_session(workload_session_id)
                alarm_result = alarm_session.execute()
                return cast(Dict[str, Any], alarm_result)

            return cast(Dict[str, Any], result)

        # No resume provided - scan for existing sessions
        existing = self.store.find_latest_for_account(
            account_id=self._account_id, exclude_alarm_creation=True
        )
        if existing:
            session_id, submission = existing
            if self._prompt_resume(submission=submission):
                if submission.workload_to_alarm_handoff:
                    self.logger.info("🚀 Resuming from alarm creation phase...")
                    alarm_session = self._create_alarm_session(session_id)
                    alarm_result = alarm_session.execute()
                    return cast(Dict[str, Any], alarm_result)
                else:
                    session = self._create_workload_session(session_id)
            else:
                session = self._create_workload_session(None)
        else:
            session = self._create_workload_session(None)

        result = session.execute()

        # Check if user chose to proceed to alarm creation
        if result.get("workflow_transition") == "alarm_creation":
            self.logger.info("🚀 Starting alarm creation phase...")
            workload_session_id = result.get("session_id")
            alarm_session = self._create_alarm_session(workload_session_id)
            alarm_result = alarm_session.execute()
            return cast(Dict[str, Any], alarm_result)

        return cast(Dict[str, Any], result)

    def _execute_from_config(
        self, config_path: str, mock_account_id: bool
    ) -> Dict[str, Any]:
        """Execute workload registration from config file."""
        with open(config_path, "r") as f:
            config = json.load(f)

        account_id = (
            "123456789012"
            if mock_account_id
            else self._sts_manager.retrieve_account_id_from_sts()
        )

        self._non_interactive_service.register_workload_from_config(config, account_id)

        return {}

    @option("--resume", "-r", help="Resume session ID")
    @option(
        "--mock-account-id",
        "-ma",
        default=False,
        help="Test option to bypass sts boto call.",
    )
    @option("--test-mode", is_flag=True, hidden=True)
    @option("--config", help="Path to JSON configuration file")
    # TODO: remove mock-account-id test option for GA or consider leaving and refactorig it.
    # @click.pass_context
    def execute(
        self,
        mock_account_id: bool,
        resume: Optional[str] = None,
        test_mode: bool = False,
        config: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Execute workload info collection."""
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

    def output(self, result: Dict[str, Any]) -> None:
        """Handle output."""
        status = result.get("status")

        if status == "completed":
            data = result.get("data", {})
            workload = data.get("workload", {})
            self.logger.info(
                f"✅ Collected info for workload: {workload.get('name', 'Unknown')}"
            )
        elif status == "paused":
            self.logger.info(
                f"Session paused. Resume with: --resume {result.get('session_id')}"
            )
