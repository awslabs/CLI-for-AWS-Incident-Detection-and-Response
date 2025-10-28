import gzip
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from cryptography.fernet import Fernet
from injector import inject

from aws_idr_customer_cli.exceptions import DirectoryCreationError, EncryptionKeyError
from aws_idr_customer_cli.interfaces.file_cache_service import FileCacheServiceInterface
from aws_idr_customer_cli.services.file_cache.data import (
    AlarmCreation,
    AlarmIngestion,
    AlarmValidation,
    OnboardingSubmission,
    WorkloadOnboard,
)
from aws_idr_customer_cli.services.file_cache.file_cache_deserializer import (
    FileCacheDeserializer,
)
from aws_idr_customer_cli.utils.constants import SCHEMA_VERSION
from aws_idr_customer_cli.utils.hash_utils import (
    calculate_dict_hash,
    calculate_submission_hash,
)
from aws_idr_customer_cli.utils.log_handlers import CliLogger


class FileCacheService(FileCacheServiceInterface):
    """File cache service implementation focusing on file operations."""

    file_cache: Optional[OnboardingSubmission] = None  # Backward compatibility

    DEFAULT_BASE_DIR = ".aws-idr"

    @inject
    def __init__(self, logger: CliLogger, deserializer: FileCacheDeserializer) -> None:
        self.logger = logger
        self.deserializer = deserializer

        self._setup_directories()
        self._init_encryption()

    def _setup_directories(self) -> None:
        """Setup directory structure."""
        self.base_dir = Path.home() / self.DEFAULT_BASE_DIR
        self.cache_dir = self.base_dir / "cache"
        self.completed_dir = self.base_dir / "completed"
        self.archive_dir = self.base_dir / "archive"

        # Create all directories
        for directory in [
            self.base_dir,
            self.cache_dir,
            self.completed_dir,
            self.archive_dir,
        ]:
            try:
                directory.mkdir(parents=True, exist_ok=True)
                os.chmod(directory, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
                self.logger.debug(f"Directory initialized: {directory}")
            except Exception as e:
                raise DirectoryCreationError(
                    f"Failed to create directory {directory}: {e}"
                ) from e

    def _init_encryption(self) -> None:
        """Auto-setup encryption."""
        key_file = self.base_dir / ".key"
        if not key_file.exists():
            try:
                key_file.write_bytes(Fernet.generate_key())
                key_file.chmod(0o600)
                self.logger.info(f"New encryption key created: {key_file}")
            except Exception as e:
                raise EncryptionKeyError(f"Failed to create encryption key: {e}") from e

        try:
            self.fernet = Fernet(key_file.read_bytes())
            self.logger.debug(f"Encryption key loaded from: {key_file}")
        except Exception as e:
            raise EncryptionKeyError(f"Failed to load encryption key: {e}") from e

    def save_submission_to_file(
        self, file_path: Path, submission: OnboardingSubmission
    ) -> bool:
        """Save with encryption and compression."""
        try:
            # Convert to dict and add hash
            data = submission.to_dict()
            data["filehash"] = calculate_dict_hash(data)

            self.logger.info(f"[Tracing] Data cached: {data}")

            # JSON -> compress -> encrypt -> save
            json_bytes = json.dumps(data, default=str).encode("utf-8")
            compressed = gzip.compress(json_bytes)
            encrypted = self.fernet.encrypt(compressed)

            file_path.write_bytes(encrypted)
            return True
        except Exception as e:
            self.logger.error(f"Error saving data to file {file_path}: {str(e)}")
            return False

    def load_file_cache(self, file_path: Path) -> Optional[OnboardingSubmission]:
        """Load with decryption and decompression."""
        if not file_path.exists():
            return None

        try:
            # Load -> decrypt -> decompress -> JSON
            encrypted_data = file_path.read_bytes()
            compressed_data = self.fernet.decrypt(encrypted_data)
            json_data = gzip.decompress(compressed_data).decode("utf-8")
            data = json.loads(json_data)
            submission = OnboardingSubmission.from_dict(data)

            if not self._verify_hash(submission):
                self.logger.warning(
                    f"Hash mismatch for file {file_path} - data may be corrupted, "
                    f"you might need to start from begining"
                )
                return None  # Corrupted

            return submission
        except Exception as e:
            self.logger.error(f"We could not load data from the previous session: {e}")
            return None

    def load_file_cache_with_schema_migration(
        self, file_path: Path
    ) -> Optional[OnboardingSubmission]:
        """Load file cache and migrate to latest schema version, if needed"""
        if not file_path.exists():
            return None

        try:
            # Load -> decrypt -> decompress -> create temp file -> deserialize
            encrypted_data = file_path.read_bytes()
            compressed_data = self.fernet.decrypt(encrypted_data)
            json_data = gzip.decompress(compressed_data).decode("utf-8")

            # Create temporary JSON file for the deserializer
            import tempfile

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            ) as temp_file:
                temp_file.write(json_data)
                temp_file_path = temp_file.name

            try:
                # Use deserializer with migration logic
                submission = self.deserializer.deserialize_file_cache(
                    temp_file_path, perform_migration=True
                )

                # Check if this was a migrated legacy cache by looking for the placeholder hash
                is_migrated_cache = submission.filehash == "migrated-cache-placeholder"

                # Return error if unmigrated cache has invalid hash
                if not is_migrated_cache and not self._verify_hash(submission):
                    self.logger.warning(
                        f"Hash mismatch for file {file_path} - data may be corrupted, "
                        f"you might need to start from begining"
                    )
                    return None

                if is_migrated_cache:
                    self.logger.info(f"Migrated legacy cache format for {file_path}")
                    submission.schema_version = SCHEMA_VERSION
                    self.update_file_cache(file_path, submission)

                return submission
            finally:
                # Clean up temp file
                os.unlink(temp_file_path)

        except Exception as e:
            self.logger.error(f"We could not load data from the previous session: {e}")
            return None

    def delete_file_cache(self, file_path: Path) -> bool:
        """Delete a file cache"""
        if not file_path.exists():
            return True  # Consider this successful (idempotent behavior)
        try:
            file_path.unlink()
            self.logger.info(f"File deleted successfully: {file_path}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete file {file_path}: {e}")
            return False

    # Property accessors for directories (for SessionStore to use)
    def get_cache_dir(self) -> Path:
        """Get cache directory path."""
        return self.cache_dir

    def get_completed_dir(self) -> Path:
        """Get completed directory path."""
        return self.completed_dir

    def get_archive_dir(self) -> Path:
        """Get archive directory path."""
        return self.archive_dir

    def get_file_path(self, session_id: str) -> Path:
        file_path = self.get_cache_dir() / f"{session_id}.enc"
        return file_path

    def _verify_hash(self, submission: OnboardingSubmission) -> bool:
        """Verify hash integrity of the data."""
        stored_hash: str = submission.filehash
        if not stored_hash:
            return False

        try:
            calculated_hash: str = calculate_submission_hash(submission)
            return stored_hash == calculated_hash
        except Exception as e:
            self.logger.debug(f"Hash verification failed: {e}")
            return False

    def update_file_cache(
        self, file_path: Path, submission: OnboardingSubmission
    ) -> bool:
        """Update an existing cache file."""
        submission.last_updated_at = datetime.now(timezone.utc)
        result = self.save_submission_to_file(file_path, submission)
        if result:
            self.file_cache = submission
        return result

    # Domain-specific getters
    def get_workload_onboarding(self) -> Optional[WorkloadOnboard]:
        """Get workload onboarding data from the file cache."""
        if self.file_cache is None:
            self.logger.debug("File cache not initialized")
            return None

        if self.file_cache.workload_onboard is None:
            self.logger.debug("Workload onboarding data not found in cache")
            return None

        return self.file_cache.workload_onboard

    def get_alarm_creation(self) -> Optional[List[AlarmCreation]]:
        """Get alarm creation data from the file cache."""
        if self.file_cache is None:
            self.logger.debug("File cache not initialized")
            return None

        if self.file_cache.alarm_creation is None:
            self.logger.debug("Alarm creation data not found in cache")
            return None

        return self.file_cache.alarm_creation  # type: ignore

    def get_alarm_validation(self) -> Optional[List[AlarmValidation]]:
        """Get alarm validation data from the file cache."""
        if self.file_cache is None:
            self.logger.debug("File cache not initialized")
            return None

        if self.file_cache.alarm_validation is None:
            self.logger.debug("Alarm validation data not found in cache")
            return None

        return self.file_cache.alarm_validation  # type: ignore

    def get_alarm_ingestion(self) -> Optional[AlarmIngestion]:
        """Get alarm ingestion data from the file cache."""
        if self.file_cache is None:
            self.logger.debug("File cache not initialized")
            return None

        if self.file_cache.alarm_ingestion is None:
            self.logger.debug("Alarm ingestion data not found in cache")
            return None

        return self.file_cache.alarm_ingestion

    # Domain-specific setters

    def put_workload_onboarding(self, file_path: Path, data: WorkloadOnboard) -> None:
        if self.file_cache is None:
            self.logger.error("File cache not initialized")
            return
        self.file_cache.workload_onboard = data
        self.update_file_cache(file_path=file_path, submission=self.file_cache)

    def put_alarm_creation(self, file_path: Path, data: List[AlarmCreation]) -> None:
        if self.file_cache is None:
            self.logger.error("File cache not initialized")
            return
        self.file_cache.alarm_creation = data
        self.update_file_cache(file_path=file_path, submission=self.file_cache)

    def put_alarm_validation(
        self, file_path: Path, data: List[AlarmValidation]
    ) -> None:
        if self.file_cache is None:
            self.logger.error("File cache not initialized")
            return
        self.file_cache.alarm_validation = data
        self.update_file_cache(file_path=file_path, submission=self.file_cache)

    def put_alarm_ingestion(self, file_path: Path, data: AlarmIngestion) -> None:
        if self.file_cache is None:
            self.logger.error("File cache not initialized")
            return
        self.file_cache.alarm_ingestion = data
        self.update_file_cache(file_path=file_path, submission=self.file_cache)

    def put_support_case_id(self, file_path: Path, caseId: str) -> None:
        if self.file_cache is None:
            self.logger.error("File cache not initialized")
            return
        if self.file_cache.workload_onboard is None:
            self.logger.error("Workload onboarding data not found")
            return
        self.file_cache.workload_onboard.support_case_id = caseId
        self.update_file_cache(file_path=file_path, submission=self.file_cache)

    def increment_session_count(self, file_path: Path) -> None:
        """Increment session count."""
        if self.file_cache is None:
            self.file_cache = self.load_file_cache_with_schema_migration(file_path)

        if self.file_cache is None:
            self.logger.error("Could not load file cache")
            return

        self.file_cache.session_count += 1
        self.update_file_cache(file_path=file_path, submission=self.file_cache)

    # Input Validation Methods -> Workload Onboarding

    def validate_workload_onboarding(self) -> bool:
        """
        Validates all required fields for workload onboarding.

        Returns:
            bool: True if all validation checks pass, False otherwise
        """
        # Check if file_cache is initialized
        if self.file_cache is None:
            return False

        # Check if workload_onboard exists
        if self.file_cache.workload_onboard is None:
            return False

        # Check workload name
        workload_name = self.file_cache.workload_onboard.name
        if not (workload_name is not None and workload_name.strip() != ""):
            return False

        # Check regions
        regions = self.file_cache.workload_onboard.regions
        if not (regions is not None and len(regions) > 0):
            return False

        # Check account ID
        accountId = self.file_cache.account_id
        if not (accountId is not None and accountId.strip() != ""):
            return False

        return True

    def is_alarm_creation_data_valid(self) -> bool:
        """
        Validates all required fields for alarm creation.
        """
        if not self.file_cache or not self.file_cache.alarm_creation:
            return False

        # TODO: validation
        return True

    def is_alarm_validation_data_valid(self) -> bool:
        """
        Validates all required fields for alarm validation.
        """
        if not self.file_cache or not self.file_cache.alarm_validation:
            return False

        # TODO: validation
        return True

    def is_alarm_ingestion_data_valid(self) -> bool:
        """
        Validates all required fields for alarm ingestion.
        """
        if not self.file_cache or not self.file_cache.alarm_ingestion:
            return False

        alarm_ingestion = self.file_cache.alarm_ingestion

        # APM ingestion has different validation requirements
        # Check if this is an APM-only submission by looking at the file cache
        if hasattr(self.file_cache, "apm_ingestion") and self.file_cache.apm_ingestion:
            return True

        if (
            not alarm_ingestion.onboarding_alarms
            or not alarm_ingestion.contacts_approval_timestamp
        ):
            return False

        for alarm in alarm_ingestion.onboarding_alarms:
            # Check alarm ARN
            if not alarm.alarm_arn or not alarm.alarm_arn.strip():
                return False

            #  Check primary contact
            if not alarm.primary_contact:
                return False

            if not (
                alarm.primary_contact.name
                or alarm.primary_contact.email
                or alarm.primary_contact.email.strip()
                or alarm.primary_contact.phone
                or alarm.primary_contact.phone.strip()
            ):
                return False

            # Check escalation contact
            if not alarm.escalation_contact:
                return False

            if not (
                alarm.escalation_contact.name
                or alarm.escalation_contact.email
                or alarm.escalation_contact.email.strip()
                or alarm.escalation_contact.phone
                or alarm.escalation_contact.phone.strip()
            ):
                return False

        return True
