import re
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Generator, List, Optional, Tuple

from aws_idr_customer_cli.interfaces.file_cache_service import FileCacheServiceInterface
from aws_idr_customer_cli.services.file_cache.data import (
    CommandStatusTracker,
    OnboardingStatus,
    OnboardingSubmission,
)
from aws_idr_customer_cli.utils.constants import CLI_VERSION, SCHEMA_VERSION
from aws_idr_customer_cli.utils.execution_mode import get_execution_mode
from aws_idr_customer_cli.utils.log_handlers import CliLogger


class SessionStore:
    """Complete session management in one class, using FileCacheService for file operations."""

    def __init__(
        self, logger: CliLogger, file_cache_service: FileCacheServiceInterface
    ) -> None:
        self.SESSION_ID_PREFIX = "idr-cx-cli_"
        self.logger = logger
        self.file_cache_service = file_cache_service
        self.current_id: Optional[str] = None

        # Ensure all directory getters are called during initialization
        self.cache_dir = self.file_cache_service.get_cache_dir()
        self.completed_dir = self.file_cache_service.get_completed_dir()
        self.archive_dir = (
            self.file_cache_service.get_archive_dir()
        )  # Add this line to fix test_initialization

    def session_id_is_valid(self, session_id: str) -> bool:
        """Validate session_id format."""
        pattern = rf"^{self.SESSION_ID_PREFIX}\d{{20}}$"
        return bool(re.match(pattern, session_id))

    # CRUD Operations

    def create(self, submission: OnboardingSubmission) -> str:
        """Create new session."""
        session_id = (
            f"{self.SESSION_ID_PREFIX}{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        )
        file_path = self.file_cache_service.get_cache_dir() / f"{session_id}.enc"

        if self.file_cache_service.save_submission_to_file(file_path, submission):
            self.current_id = session_id
            return session_id

        raise RuntimeError("Failed to create session")

    def get(self, session_id: str) -> Optional[OnboardingSubmission]:
        """Get session by ID."""
        if not self.session_id_is_valid(session_id):
            self.logger.error(
                f"Invalid session ID: {session_id} \
                Please make sure the session ID starts with {self.SESSION_ID_PREFIX} \
                followed by a 20-digit timestamp, example:\
                'idr-cx-cli_2025062320304754603'."
            )
            return None

        for directory in [
            self.file_cache_service.get_cache_dir(),
            self.file_cache_service.get_completed_dir(),
        ]:
            file_path = directory / f"{session_id}.enc"
            submission = self.file_cache_service.load_file_cache_with_schema_migration(
                file_path
            )
            if submission:
                self.current_id = session_id
                return submission

        # Log error for corrupted session
        self.logger.error(f"Session {session_id} not found or corrupted")
        return None

    def update(self, session_id: str, submission: OnboardingSubmission) -> bool:
        """Update existing session."""
        for directory in [
            self.file_cache_service.get_cache_dir(),
            self.file_cache_service.get_completed_dir(),
        ]:
            file_path = directory / f"{session_id}.enc"
            if file_path.exists():
                return self.file_cache_service.update_file_cache(  # type: ignore
                    file_path, submission
                )
        return False

    def delete(self, session_id: str) -> bool:
        """Delete session."""
        deleted = False

        for directory in [
            self.file_cache_service.get_cache_dir(),
            self.file_cache_service.get_completed_dir(),
            self.file_cache_service.get_archive_dir(),
        ]:
            file_path = directory / f"{session_id}.enc"
            if file_path.exists():
                if self.file_cache_service.delete_file_cache(file_path):
                    deleted = True

        if deleted and session_id == self.current_id:
            self.current_id = None

        return deleted

    # Query Operations

    def list_all(
        self, status: Optional[OnboardingStatus] = None
    ) -> List[Tuple[str, OnboardingSubmission]]:
        """List sessions with optional status filter."""
        result = []

        dirs_to_scan = []
        if not status or status == OnboardingStatus.IN_PROGRESS:
            dirs_to_scan.append(self.file_cache_service.get_cache_dir())
        if not status or status == OnboardingStatus.COMPLETED:
            dirs_to_scan.append(self.file_cache_service.get_completed_dir())

        for directory in dirs_to_scan:
            for file_path in directory.glob("*.enc"):
                submission = (
                    self.file_cache_service.load_file_cache_with_schema_migration(
                        file_path
                    )
                )
                if submission and (not status or submission.status == status):
                    session_id = file_path.stem
                    result.append((session_id, submission))

        return sorted(result, key=lambda x: x[1].last_updated_at, reverse=True)

    def get_in_progress(self) -> List[Tuple[str, OnboardingSubmission]]:
        """Get all in-progress sessions."""
        return self.list_all(OnboardingStatus.IN_PROGRESS)

    def find_latest_for_account(
        self, account_id: str, exclude_alarm_creation: bool = False
    ) -> Optional[Tuple[str, OnboardingSubmission]]:
        """Find latest session for account."""
        sessions = [
            (sid, sub)
            for sid, sub in self.get_in_progress()
            if sub.account_id == account_id
            and (not exclude_alarm_creation or sub.progress.alarm_creation is None)
        ]
        return sessions[0] if sessions else None

    @staticmethod
    def _is_alarm_creation_ready(sub: OnboardingSubmission) -> bool:
        """Check if session is ready for alarm creation."""
        # alarm creation started
        if sub.progress.alarm_creation:
            return True

        if sub.workload_onboard and sub.workload_onboard.support_case_id:
            return True

        return False

    def find_latest_alarm_ready_session(
        self, account_id: str
    ) -> Optional[Tuple[str, OnboardingSubmission]]:
        """Find latest session ready for alarm creation."""
        sessions = [
            (sid, sub)
            for sid, sub in self.get_in_progress()
            if sub.account_id == account_id and self._is_alarm_creation_ready(sub)
        ]
        return sessions[0] if sessions else None

    @staticmethod
    def _is_alarm_ingestion_ready(sub: OnboardingSubmission) -> bool:
        if sub.progress.alarm_ingestion:
            return True

        if sub.workload_onboard and sub.workload_contacts:
            return True

        return False

    def find_latest_alarm_ingestion_session(
        self, account_id: str
    ) -> Optional[Tuple[str, OnboardingSubmission]]:
        sessions = [
            (sid, sub)
            for sid, sub in self.get_in_progress()
            if sub.account_id == account_id and self._is_alarm_ingestion_ready(sub)
        ]
        return sessions[0] if sessions else None

    def find_latest_apm_session(
        self, account_id: str
    ) -> Optional[Tuple[str, OnboardingSubmission]]:
        """Find latest APM setup session for account."""
        sessions = [
            (sid, sub)
            for sid, sub in self.get_in_progress()
            if sub.account_id == account_id and sub.apm_setup is not None
        ]
        return sessions[0] if sessions else None

    # Lifecycle Operations

    def complete(self, session_id: str) -> bool:
        """Mark session complete and move to completed directory."""
        submission = self.get(session_id)
        if not submission:
            return False

        submission.status = OnboardingStatus.COMPLETED
        submission.last_updated_at = datetime.now(timezone.utc)

        # save  to completed dir and remove from cache
        completed_path = (
            self.file_cache_service.get_completed_dir() / f"{session_id}.enc"
        )
        cache_path = self.file_cache_service.get_cache_dir() / f"{session_id}.enc"

        if self.file_cache_service.save_submission_to_file(completed_path, submission):
            self.file_cache_service.delete_file_cache(cache_path)
            return True
        return False

    def archive_old(self, days_threshold: int = 30) -> int:
        """Archive sessions older than threshold."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_threshold)
        count = 0

        for directory in [
            self.file_cache_service.get_cache_dir(),
            self.file_cache_service.get_completed_dir(),
        ]:
            for file_path in directory.glob("*.enc"):
                mtime = datetime.fromtimestamp(
                    file_path.stat().st_mtime, tz=timezone.utc
                )
                if mtime < cutoff:
                    archive_path = (
                        self.file_cache_service.get_archive_dir() / file_path.name
                    )
                    file_path.rename(archive_path)
                    count += 1

        return count

    @contextmanager
    def new_session(
        self, account_id: str
    ) -> Generator[Tuple[str, OnboardingSubmission], None, None]:
        """Create NEW session - explicit intent."""
        submission = OnboardingSubmission(
            filehash="",
            schema_version=SCHEMA_VERSION,
            idr_cli_version=CLI_VERSION,
            account_id=account_id,
            status=OnboardingStatus.IN_PROGRESS,
            created_at=datetime.now(timezone.utc),
            last_updated_at=datetime.now(timezone.utc),
            execution_mode=get_execution_mode(),
            progress=CommandStatusTracker(),
        )

        session_id = self.create(submission)

        try:
            yield session_id, submission
        finally:
            self.update(session_id, submission)

    @contextmanager
    def existing_session(
        self, session_id: str
    ) -> Generator[Tuple[str, OnboardingSubmission], None, None]:
        """Work with EXISTING session - explicit intent."""
        submission = self.get(session_id)
        if not submission:
            raise ValueError(f"Session {session_id} not found")

        try:
            yield session_id, submission
        finally:
            self.update(session_id, submission)
