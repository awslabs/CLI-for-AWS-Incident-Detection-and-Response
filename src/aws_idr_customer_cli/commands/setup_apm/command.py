from typing import Any, Dict, Optional

import click
from injector import inject

from aws_idr_customer_cli.clients.iam import BotoIamManager
from aws_idr_customer_cli.clients.sts import BotoStsManager
from aws_idr_customer_cli.core.command_base import CommandBase
from aws_idr_customer_cli.core.decorators import command, option
from aws_idr_customer_cli.core.interactive.ui import InteractiveUI
from aws_idr_customer_cli.services.apm.apm_service import ApmService
from aws_idr_customer_cli.services.file_cache.data import OnboardingSubmission
from aws_idr_customer_cli.services.file_cache.file_cache_service import FileCacheService
from aws_idr_customer_cli.services.support_case_service import SupportCaseService
from aws_idr_customer_cli.utils.apm.apm_constants import (
    GENERATE_ONLY_FORMAT_CHOICES,
    GENERATE_ONLY_FORMAT_DEFAULT,
)
from aws_idr_customer_cli.utils.log_handlers import CliLogger
from aws_idr_customer_cli.utils.session.apm_setup_session import ApmSetupSession
from aws_idr_customer_cli.utils.session.session_store import SessionStore
from aws_idr_customer_cli.utils.validation.apm_validation import (
    ApmPrerequisiteValidator,
)
from aws_idr_customer_cli.utils.validation.validator import Validate


@command("setup-apm")
class SetupApm(CommandBase):
    """Set up integration between 3rd party APM providers and AWS account.

    Examples:

    \b
        awsidr setup-apm
        awsidr setup-apm --resume {sessionId}
        awsidr setup-apm --verbose
        awsidr setup-apm --debug
        awsidr setup-apm --generate-template-only
        awsidr setup-apm --generate-template-only -o ./infra/idr-apm.json
        awsidr setup-apm --generate-template-only --format yaml
    """

    @inject
    def __init__(
        self,
        logger: CliLogger,
        ui: InteractiveUI,
        sts_manager: BotoStsManager,
        iam_manager: BotoIamManager,
        store: SessionStore,
        apm_service: ApmService,
        file_cache_service: FileCacheService,
        support_case_service: SupportCaseService,
        validator: Validate,
    ) -> None:
        self.logger = logger
        self.ui = ui
        self.apm_service = apm_service
        self.file_cache_service = file_cache_service
        self.support_case_service = support_case_service
        self.sts_manager = sts_manager
        self.iam_manager = iam_manager
        self.store = store
        self.validator = validator
        self._account_id: Optional[str] = None
        self._generate_template_only: bool = False
        self._output_template: Optional[str] = None
        self._output_format: str = GENERATE_ONLY_FORMAT_DEFAULT

    @option("--resume", "-r", help="Resume from existing session ID")
    @option(
        "--generate-template-only",
        "generate_template_only",
        is_flag=True,
        default=False,
        help=(
            "Generate the CloudFormation template and parameters to disk and "
            "exit without deploying (no AWS resources are created)."
        ),
    )
    @option(
        "--output-template",
        "-o",
        "output_template",
        type=click.Path(dir_okay=False, writable=True),
        default=None,
        help=(
            "Output path for the generated template (only valid with "
            "--generate-template-only; "
            "defaults to ./awsidr-apm-<provider>-template.json)."
        ),
    )
    @option(
        "--format",
        "output_format",
        type=click.Choice(list(GENERATE_ONLY_FORMAT_CHOICES)),
        default=GENERATE_ONLY_FORMAT_DEFAULT,
        show_default=True,
        help=(
            "Output format for the generated CloudFormation template (only "
            "valid with --generate-template-only). The parameters file is "
            "always JSON, as required by CloudFormation."
        ),
    )
    def execute(
        self,
        resume: Optional[str] = None,
        generate_template_only: bool = False,
        output_template: Optional[str] = None,
        output_format: str = GENERATE_ONLY_FORMAT_DEFAULT,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Execute the setup-apm command."""
        try:
            if output_template and not generate_template_only:
                return {
                    "status": "error",
                    "message": (
                        "--output-template/-o can only be used together with "
                        "--generate-template-only."
                    ),
                }

            # Detect whether --format was actually supplied rather than
            # comparing to the default: --format json (== default) would
            # otherwise be silently accepted without --generate-template-only,
            # inconsistent with -o which errors whenever provided.
            ctx = click.get_current_context(silent=True)
            format_provided = (
                ctx is not None
                and ctx.get_parameter_source("output_format")
                != click.core.ParameterSource.DEFAULT
            )
            if format_provided and not generate_template_only:
                return {
                    "status": "error",
                    "message": (
                        "--format can only be used together with "
                        "--generate-template-only."
                    ),
                }

            self._generate_template_only = generate_template_only
            self._output_template = output_template
            self._output_format = output_format
            return self._execute_business_logic(resume, **kwargs)
        except Exception as e:
            self.logger.error(f"APM setup failed: {e}")
            return {"status": "error", "message": f"APM setup failed: {str(e)}"}

    def _execute_business_logic(
        self,
        resume: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Execute APM setup business logic with session management."""
        self._account_id = self.sts_manager.retrieve_account_id_from_sts()

        # Generate-only mode has no resume: it runs the interactive flow once
        # and writes a template file instead of persisting a resumable deploy
        # step. Never resume an existing session or prompt to resume one here —
        # always start fresh, even if --resume was passed.
        if self._generate_template_only:
            session = self._create_apm_session(resume_session_id=None)
            result = session.execute()
            return self._handle_session_result(result, session)

        if resume:
            session = self._create_apm_session(resume_session_id=resume)
            result = session.execute()
            return self._handle_session_result(result, session)

        existing = self.store.find_latest_apm_session(self._account_id)
        if existing:
            session_id, submission = existing
            if self._prompt_resume_apm(submission=submission):
                session = self._create_apm_session(resume_session_id=session_id)
                result = session.execute()
                return self._handle_session_result(result, session)
            else:
                # Start fresh
                session = self._create_apm_session(resume_session_id=None)
                result = session.execute()
                return self._handle_session_result(result, session)
        else:
            session = self._create_apm_session(resume_session_id=None)
            result = session.execute()
            return self._handle_session_result(result, session)

    def _handle_session_result(
        self, result: Dict[str, Any], session: Optional[ApmSetupSession] = None
    ) -> Dict[str, Any]:
        """Handle session execution result and convert to command result."""
        status = result.get("status")

        # Generate-only: the session stops at the push step by design, having
        # written the template instead of deploying it. That is a success.
        if session is not None and getattr(session, "template_exported", False):
            return {
                "status": "success",
                "template_only": True,
                "output_path": session.template_output_path,
                "parameters_path": session.template_parameters_path,
            }

        if status == "completed":
            return {
                "status": "success",
                "submission": result.get("submission"),
            }
        elif status == "quit":
            # Generate-only has no resume, so never tell the user to resume.
            if session is not None and getattr(
                session, "generate_template_only", False
            ):
                return {
                    "status": "cancelled",
                    "message": (
                        "Generate-only run stopped before completing; no "
                        "resumable session was saved. Re-run "
                        "awsidr setup-apm --generate-template-only."
                    ),
                }
            return {
                "status": "cancelled",
                "message": "APM setup stopped. Address the issues above and resume setup.",
                "session_id": result.get("session_id"),
            }
        else:
            return {
                "status": "error",
                "message": "APM setup encountered an unexpected state.",
                "result": result,
            }

    def _create_apm_session(
        self, resume_session_id: Optional[str] = None
    ) -> ApmSetupSession:
        """Create APM setup session with real account ID."""
        apm_validator = ApmPrerequisiteValidator(
            base_validator=self.validator,
            eventbridge_accessor=self.apm_service.eventbridge_accessor,
            sns_accessor=self.apm_service.sns_accessor,
        )

        return ApmSetupSession(
            store=self.store,
            apm_service=self.apm_service,
            file_cache_service=self.file_cache_service,
            support_case_service=self.support_case_service,
            iam_manager=self.iam_manager,
            apm_validator=apm_validator,
            account_id=self._account_id,
            resume_session_id=resume_session_id,
            generate_template_only=self._generate_template_only,
            output_path=self._output_template,
            output_format=self._output_format,
        )

    def _prompt_resume_apm(self, submission: OnboardingSubmission) -> bool:
        """Prompt user to resume existing APM session."""
        self.ui.display_header(
            "Found Existing APM Setup Session",
            "Review the details below to decide whether to continue or start fresh:",
        )

        self._display_apm_session_summary(submission)
        self._display_apm_progress_status(submission)

        return bool(
            self.ui.prompt_confirm(
                "Would you like to resume your session?",
                default=True,
            )
        )

    def _display_apm_session_summary(self, submission: OnboardingSubmission) -> None:
        """Display APM session summary."""
        if submission.apm_setup:
            apm = submission.apm_setup
            self.ui.display_result(
                "🔧 APM Setup Details",
                {
                    "Provider": apm.provider or "(not selected)",
                    "Integration ARN": (
                        apm.partner_event_source_arn
                        or apm.sns_topic_arn
                        or "(not configured)"
                    ),
                    "Resources Created": (
                        f"{len(apm.resources)} items" if apm.resources else "None"
                    ),
                    "Alert Identifiers": (
                        f"{len(apm.alert_identifiers)} configured"
                        if apm.alert_identifiers
                        else "None"
                    ),
                },
            )

    def _display_apm_progress_status(self, submission: OnboardingSubmission) -> None:
        """Display APM setup progress."""
        if submission.progress.apm_setup:
            tracker = submission.progress.apm_setup
            step_descriptions = ApmSetupSession.get_step_names()
            current_step = tracker.current_step
            total_steps = len(step_descriptions)

            if current_step >= total_steps:
                self.ui.display_info("✅ APM setup completed!", style="green")
            else:
                progress_bar = "█" * current_step + "░" * (total_steps - current_step)
                self.ui.display_info(
                    f"🔄 APM Setup Progress: {progress_bar} ({current_step}/{total_steps})",
                    style="blue",
                )

                if current_step > 0:
                    last_completed = step_descriptions[current_step - 1]
                    self.ui.display_info(
                        f"✅ Last Completed: {last_completed}", style="dim"
                    )

                if current_step < len(step_descriptions):
                    next_step = step_descriptions[current_step]
                    self.ui.display_info(f"🎯 Next Step: {next_step}", style="green")

    def output(self, result: Dict[str, Any]) -> None:
        """Handle command output."""
        if result["status"] == "success":
            pass
        elif result["status"] == "cancelled":
            click.secho(f"⚠️  {result['message']}", fg="yellow")
        elif result["status"] == "error":
            click.secho(f"✗ {result['message']}", fg="red")
