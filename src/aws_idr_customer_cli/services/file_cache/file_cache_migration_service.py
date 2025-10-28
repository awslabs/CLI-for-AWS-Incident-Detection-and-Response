from typing import Any, Dict, Tuple

from aws_idr_customer_cli.utils.constants import SCHEMA_VERSION


class FileCacheMigrationService:
    """Service for handling file cache format migrations."""

    @property
    def CURRENT_REGISTER_WORKLOAD_TOTAL_STEPS(self) -> int:
        # Lazy import to avoid circular dependency
        from aws_idr_customer_cli.utils.session.workload_session import WorkloadSession

        return len(WorkloadSession.get_step_names())

    @property
    def CURRENT_ALARM_CREATION_TOTAL_STEPS(self) -> int:
        # Lazy import to avoid circular dependency
        from aws_idr_customer_cli.utils.session.alarm_creation_session import (
            AlarmCreationSession,
        )

        return len(AlarmCreationSession.get_step_names())

    def migrate_if_needed(
        self, data: Dict[str, Any], perform_migration: bool = True
    ) -> Tuple[Dict[str, Any], bool]:
        """
        Migrate cache data if needed and if migration is enabled.

        Args:
            data: Raw cache data dictionary
            perform_migration: Whether to perform migration (default True)

        Returns:
            Tuple of (potentially migrated data, whether migration was performed)
        """
        if not perform_migration:
            return data, False

        # Skip migration if already current schema version
        current_schema = data.get("schema_version", "1")  # default to "1" for legacy
        if current_schema == SCHEMA_VERSION:
            return data, False

        return data, self._migrate_legacy_cache_format_v1(data)

    def _migrate_legacy_cache_format_v1(self, data: Dict[str, Any]) -> bool:
        """
        Migrate legacy cache format to current format for backward compatibility.

        Handles migration from SCHEMA_VERSION V1 format:
        - workload_contacts -> alarm_contacts (only if alarm_contacts doesn't exist)
        - Remove deprecated workload_onboard fields (description, enterprise_name)
        - Migrate step numbers from legacy workflow structures
        - Set placeholder filehash for migrated data

        Args:
            data: Raw cache data dictionary (modified in place)

        Returns:
            bool: True if migration was performed, False otherwise
        """
        migration_needed = False

        if "workload_contacts" in data:
            if "alarm_contacts" not in data:
                data["alarm_contacts"] = data["workload_contacts"]
                migration_needed = True
            del data["workload_contacts"]
            migration_needed = True

        if "workload_onboard" in data and isinstance(data["workload_onboard"], dict):
            workload_data = data["workload_onboard"]
            if "description" in workload_data:
                workload_data.pop("description", None)
                migration_needed = True
            if "enterprise_name" in workload_data:
                workload_data.pop("enterprise_name", None)
                migration_needed = True

        if migration_needed:
            self._migrate_step_numbers(data)
            data["filehash"] = (
                "migrated-cache-placeholder"  # filehash is recalculated after migration
            )

        return migration_needed

    def _migrate_step_numbers(self, data: Dict[str, Any]) -> None:
        """
        Reset current step to 1 after schema migration.
        The CLI will display previous values as defaults

        Args:
            data: Raw cache data dictionary (modified in place)

        Returns:
            None
        """

        if "progress" in data and isinstance(data["progress"], dict):
            progress_data = data["progress"]

            # Reset workload registration to step 1
            if (
                "workload_registration" in progress_data
                and progress_data["workload_registration"]
            ):
                workload_tracker = progress_data["workload_registration"]
                if isinstance(workload_tracker, dict):
                    workload_tracker["current_step"] = 0  # 0-indexed, so step 1
                    workload_tracker["total_steps"] = (
                        self.CURRENT_REGISTER_WORKLOAD_TOTAL_STEPS
                    )

            # Reset alarm creation to step 1
            if "alarm_creation" in progress_data and progress_data["alarm_creation"]:
                alarm_tracker = progress_data["alarm_creation"]
                if isinstance(alarm_tracker, dict):
                    alarm_tracker["current_step"] = 0  # 0-indexed, so step 1
                    alarm_tracker["total_steps"] = (
                        self.CURRENT_ALARM_CREATION_TOTAL_STEPS
                    )
