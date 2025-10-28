from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

from aws_idr_customer_cli.services.file_cache.data import (
    AlarmCreation,
    AlarmIngestion,
    AlarmValidation,
    OnboardingSubmission,
    WorkloadOnboard,
)


class FileCacheServiceInterface(ABC):
    """Interface for managing file caches with encryption and compression support."""

    @abstractmethod
    def update_file_cache(
        self, file_path: Path, submission: OnboardingSubmission
    ) -> bool:
        """Update an existing cache file."""
        pass

    @abstractmethod
    def save_submission_to_file(
        self, file_path: Path, submission: OnboardingSubmission
    ) -> bool:
        """Save submission data with encryption and compression."""
        pass

    @abstractmethod
    def load_file_cache(self, file_path: Path) -> Optional[OnboardingSubmission]:
        """Load submission data with decryption and decompression."""
        pass

    @abstractmethod
    def load_file_cache_with_schema_migration(
        self, file_path: Path
    ) -> Optional[OnboardingSubmission]:
        """Load file cache and migrate to latest schema version, if needed."""
        pass

    @abstractmethod
    def delete_file_cache(self, file_path: Path) -> bool:
        """Delete a cache file."""
        pass

    # Directory getters
    @abstractmethod
    def get_archive_dir(self) -> Path:
        pass

    @abstractmethod
    def get_cache_dir(self) -> Path:
        pass

    @abstractmethod
    def get_completed_dir(self) -> Path:
        pass

    @abstractmethod
    def get_workload_onboarding(self) -> Optional[WorkloadOnboard]:
        pass

    @abstractmethod
    def get_alarm_creation(self) -> Optional[List[AlarmCreation]]:
        pass

    @abstractmethod
    def get_alarm_validation(self) -> Optional[List[AlarmValidation]]:
        pass

    @abstractmethod
    def get_alarm_ingestion(self) -> Optional[AlarmIngestion]:
        pass

    @abstractmethod
    def put_workload_onboarding(self, file_path: Path, data: WorkloadOnboard) -> None:
        pass

    @abstractmethod
    def put_alarm_creation(self, file_path: Path, data: List[AlarmCreation]) -> None:
        pass

    @abstractmethod
    def put_alarm_validation(
        self, file_path: Path, data: List[AlarmValidation]
    ) -> None:
        pass

    @abstractmethod
    def put_alarm_ingestion(self, file_path: Path, data: AlarmIngestion) -> None:
        pass
