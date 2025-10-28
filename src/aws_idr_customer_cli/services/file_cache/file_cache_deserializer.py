import json
import os
from datetime import datetime
from typing import Any

from aws_idr_customer_cli.services.file_cache.data import (
    OnboardingSubmission,
)
from aws_idr_customer_cli.services.file_cache.file_cache_migration_service import (
    FileCacheMigrationService,
)


class FileCacheDeserializeError(Exception):
    def __init__(self, message: str, file_path: str) -> None:
        self.file_path = file_path
        err_msg = f"{message}. File path: {file_path}"
        super().__init__(self, err_msg)


class FileCacheDeserializer:

    def __init__(self) -> None:
        self.migration_service = FileCacheMigrationService()

    @staticmethod
    def _deserialize_datetime(dt_str: str) -> datetime:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))

    @staticmethod
    def _parse_json_file(json_file_path: str) -> Any:
        try:
            if not os.path.exists(json_file_path):
                raise FileCacheDeserializeError("Invalid file path.\n", json_file_path)

            with open(json_file_path, "r") as f:
                return json.loads(f.read())

        except json.JSONDecodeError as e:
            raise FileCacheDeserializeError(
                f"Invalid JSON format: {str(e)}\n", json_file_path
            )

    def deserialize_file_cache(
        self, json_file_path: str, perform_migration: bool = True
    ) -> OnboardingSubmission:
        """
        Deserialize JSON string to OnboardingSubmission class with legacy format support.

        Args:
            json_file_path: A JSON file path containing submission data
            perform_migration: Whether to perform migration (default True)

        Returns:
            OnboardingSubmission object
        """

        data = self._parse_json_file(json_file_path)

        # Use migration service to handle legacy format migration
        data, migration_performed = self.migration_service.migrate_if_needed(
            data, perform_migration
        )

        return OnboardingSubmission.from_dict(data)  # type: ignore
