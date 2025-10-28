from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, cast

from typing_extensions import Protocol

from aws_idr_customer_cli.core.interactive.ui import InteractiveUI
from aws_idr_customer_cli.services.file_cache.data import (
    OnboardingSubmission,
    ProgressTracker,
)
from aws_idr_customer_cli.utils.constants import (
    CommandType,
    SessionKeys,
)
from aws_idr_customer_cli.utils.session.session_store import SessionStore

# CONSTANTS

# Step metadata keys
STEP_IS_STEP = "_is_step"
STEP_NAME = "_step_name"
STEP_ORDER = "_step_order"

WORKLOAD = "workload"
RESOURCES = "resources"
ALARM_VALIDATION = "alarm_validation"
ALARM_INGESTION = "alarm_ingestion"

# Action types
ACTION_KEY = "action"
ACTION_BACK = "back"
ACTION_RETRY = "retry"
ACTION_SKIP = "skip"
ACTION_QUIT = "quit"
ACTION_PAUSE = "pause"


# Status as enum
class SessionStatus(str, Enum):
    COMPLETED = "completed"
    PAUSED = "paused"
    QUIT = "quit"


# Dictionary keys
STATUS_KEY = "status"
SUBMISSION_KEY = "submission"
DATA_KEY = "data"
SESSION_ID_KEY = "session_id"

# UI styles
STYLE_BLUE = "blue"
STYLE_DIM = "dim"
STYLE_GREEN = "green"
STYLE_YELLOW = "yellow"

# Messages
MSG_SESSION_NOT_FOUND = "Session {} not found"
MSG_RESTORED_DATA = "Restored data from submission"
MSG_RESUMING_SESSION = "Resuming session from step {}/{}"
MSG_AVAILABLE_DATA = "Available data: {}"
MSG_STEP_PROGRESS = "Step {}/{}: {}"
MSG_AC_SESSION_COMPLETED = (
    " ✅ IDR onboarding session completed - your alarms are being processed! "
)
MSG_AI_SESSION_COMPLETED = " ✅ Alarm ingestion completed successfully"
MSG_WO_SESSION_COMPLETED = " ✅ IDR Workload Onboarding request submitted"
MSG_APM_SESSION_COMPLETED = " ✅  APM setup integration is complete"
MSG_SESSION_PAUSED = "\nSession paused. Resume with: --resume {}"


# CORE CLASSES
class StepFunction(Protocol):
    """Protocol for step functions with metadata."""

    _is_step: bool
    _step_name: str
    _step_order: int

    def __call__(self) -> Any: ...


def session_step(
    name: str, order: int = 0
) -> Callable[[Callable[..., Any]], StepFunction]:
    """Decorator to mark methods as session steps."""

    def decorator(func: Callable[..., Any]) -> StepFunction:
        setattr(func, STEP_IS_STEP, True)
        setattr(func, STEP_NAME, name)
        setattr(func, STEP_ORDER, order)
        return func  # type: ignore

    return decorator


class InteractiveSession(ABC):
    """Minimalist session framework."""

    def __init__(
        self,
        session_type: CommandType,
        account_id: str,
        store: SessionStore,
        resume_session_id: Optional[str] = None,
    ) -> None:
        self.session_type = session_type
        self.account_id = account_id
        self.ui: InteractiveUI = InteractiveUI()
        self.store = store
        # Single source of truth
        self.submission: Optional[OnboardingSubmission] = None
        self.current_step: int = 0
        self.session_id: Optional[str] = None
        self.steps = self._discover_steps()

        if resume_session_id:
            self._resume_session(resume_session_id)
        else:
            self._init_new_session()

    @classmethod
    def get_step_names(cls) -> List[str]:
        """Get step names from this session class."""
        steps = []

        # step decorators inspection
        for name in dir(cls):
            method = getattr(cls, name)
            if hasattr(method, STEP_IS_STEP) and getattr(method, STEP_IS_STEP):
                steps.append(method)

        steps.sort(key=lambda s: (getattr(s, STEP_ORDER), getattr(s, STEP_NAME)))

        # Return names
        return [getattr(step, STEP_NAME) for step in steps]

    def _discover_steps(self) -> List[StepFunction]:
        """Auto-discover step methods."""
        steps = [
            getattr(self, name)
            for name in dir(self)
            if hasattr(getattr(self, name), STEP_IS_STEP)
        ]
        return sorted(
            steps, key=lambda s: (getattr(s, STEP_ORDER), getattr(s, STEP_NAME))
        )

    def _init_new_session(self) -> None:
        """Initialize new session."""
        with self.store.new_session(self.account_id) as (session_id, submission):
            self.session_id = session_id
            self.submission = submission
            self._get_progress_tracker()

    def _resume_session(self, resume_session_id: str) -> None:
        """Resume existing session."""
        submission = self.store.get(resume_session_id)
        if not submission:
            raise ValueError(MSG_SESSION_NOT_FOUND.format(resume_session_id))

        self.session_id = resume_session_id
        self.submission = submission
        tracker = self._get_progress_tracker()
        self.current_step = tracker.current_step

        file_path = self.store.file_cache_service.get_file_path(resume_session_id)
        self.store.file_cache_service.increment_session_count(file_path)
        self.submission = self.store.file_cache_service.file_cache

        self._display_resume_info()

    def _get_progress_tracker(self) -> ProgressTracker:
        """Get or create the correct progress tracker using direct field access."""
        if not self.submission:
            raise RuntimeError("No submission available")

        # "workload_registration" or "alarm_creation"
        field_name = self.session_type

        tracker = getattr(self.submission.progress, field_name)
        if not tracker:
            tracker = ProgressTracker(
                total_steps=len(self.steps),
            )
            setattr(self.submission.progress, field_name, tracker)
        return tracker

    def _get_available_data_summary(self) -> List[str]:
        """Get summary of available data in submission."""
        if not self.submission:
            return []

        available = []

        # Check workload data
        if self.submission.workload_onboard:
            available.append(WORKLOAD)

        # Check resources
        if self.submission.resource_arns_selected:
            available.append(RESOURCES)

        # Check alarm data
        if self.submission.alarm_creation:
            available.append(SessionKeys.ALARM_CREATION.value)

        if self.submission.alarm_validation:
            available.append(ALARM_VALIDATION)

        if self.submission.alarm_ingestion:
            available.append(ALARM_INGESTION)

        return available

    @abstractmethod
    def _display_resume_info(self) -> None:
        """
        The child classes implement these because
        they have context of the steps
        """
        pass

    def execute_step(
        self, step_name: str, step_func: Callable[[], Any]
    ) -> Dict[str, Any]:
        """Execute single step."""
        self.ui.display_header(title=step_name)
        try:
            step_func()
            self._save_progress()
            return {
                STATUS_KEY: SessionStatus.COMPLETED,
                SUBMISSION_KEY: self.submission,
            }
        except KeyboardInterrupt:
            self._save_progress()
            return {
                STATUS_KEY: SessionStatus.PAUSED,
                SESSION_ID_KEY: self.session_id,
            }

    def execute(self) -> Dict[str, Any]:
        """Execute session with auto-save and navigation."""
        try:
            while self.current_step < len(self.steps):
                if not self._execute_current_step():
                    return self._save_and_quit()
            return self._complete_session()
        except KeyboardInterrupt:
            return self._pause_session()

    def _execute_current_step(self) -> bool:
        """Execute current step and handle navigation. Returns False to quit."""
        step = self.steps[self.current_step]
        step_name = getattr(step, STEP_NAME)

        self.ui.display_info(
            message=MSG_STEP_PROGRESS.format(
                self.current_step + 1, len(self.steps), step_name
            )
        )

        result = step()

        if isinstance(result, dict):
            action = result.get(ACTION_KEY)
            if "workflow_transition" in result:
                setattr(self, "_workflow_transition", result["workflow_transition"])

            if action == ACTION_BACK and self.current_step > 0:
                self.current_step -= 1
                self._save_progress()
                return True
            elif action == ACTION_RETRY:
                self._save_progress()
                return True
            elif (
                action == ACTION_QUIT
                or action == ACTION_PAUSE
                or result.get("workflow_transition")
            ):
                return False

        self.current_step += 1
        self._save_progress()
        return True

    def _save_progress(self) -> None:
        """Save current progress after each step."""
        if not self.session_id or not self.submission:
            return

        tracker = self._get_progress_tracker()
        tracker.current_step = self.current_step
        tracker.total_steps = len(self.steps)

        # write happens here at the end of each step
        self.store.update(session_id=self.session_id, submission=self.submission)

    def _complete_session(self) -> Dict[str, Any]:
        """Mark session complete."""
        if self.session_id:
            self.store.complete(self.session_id)

        if self.session_type == CommandType.ALARM_CREATION:
            message = MSG_AC_SESSION_COMPLETED
        elif self.session_type == CommandType.ALARM_INGESTION:
            message = MSG_AI_SESSION_COMPLETED
        elif self.session_type == CommandType.APM_SETUP:
            message = MSG_APM_SESSION_COMPLETED
        else:
            message = MSG_WO_SESSION_COMPLETED

        self.ui.display_info(message=message, style=STYLE_GREEN)

        return {
            STATUS_KEY: SessionStatus.COMPLETED,
            SUBMISSION_KEY: self.submission,
        }

    def _pause_session(self) -> Dict[str, Any]:
        """Pause session."""
        self._save_progress()
        self.ui.display_info(
            message=MSG_SESSION_PAUSED.format(self.session_id), style=STYLE_YELLOW
        )
        return {
            STATUS_KEY: SessionStatus.PAUSED,
            SESSION_ID_KEY: self.session_id,
        }

    def _save_and_quit(self) -> Dict[str, Any]:
        """Save and quit."""
        self._save_progress()
        result = {
            STATUS_KEY: SessionStatus.QUIT,
            SESSION_ID_KEY: self.session_id,
        }

        if hasattr(self, "_workflow_transition"):
            result["workflow_transition"] = getattr(self, "_workflow_transition")

        return result

    def get_workload_name(self) -> str:
        """Helper method to get workload name for display purposes."""
        if (
            self.submission
            and self.submission.workload_onboard
            and self.submission.workload_onboard.name
        ):
            return cast(str, self.submission.workload_onboard.name)
        return "Unknown Workload"

    def get_resource_count(self) -> int:
        """Helper method to get resource count."""
        if self.submission and self.submission.resource_arns_selected:
            return len(self.submission.resource_arns_selected)
        return 0

    def has_workload_data(self) -> bool:
        """Check if workload data exists."""
        return (
            self.submission is not None and self.submission.workload_onboard is not None
        )

    def has_resource_data(self) -> bool:
        """Check if resource data exists."""
        return (
            self.submission is not None
            and self.submission.resource_arns_selected is not None
            and len(self.submission.resource_arns_selected) > 0
        )

    def has_alarm_creation_data(self) -> bool:
        """Check if alarm creation data exists."""
        return (
            self.submission is not None and self.submission.alarm_creation is not None
        )
