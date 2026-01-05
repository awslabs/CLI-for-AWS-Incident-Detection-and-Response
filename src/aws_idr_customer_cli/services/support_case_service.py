from pathlib import Path
from typing import Any, Dict, Optional, cast

from injector import inject

from aws_idr_customer_cli.data_accessors.support_case_accessor import (
    SupportCaseAccessor,
)
from aws_idr_customer_cli.exceptions import (
    AlarmCreationValidationError,
    AlarmIngestionValidationError,
    SupportCaseAlreadyExistsError,
    SupportCaseNotFoundError,
)
from aws_idr_customer_cli.services.file_cache.data import (
    OnboardingSubmission,
    WorkloadOnboard,
)
from aws_idr_customer_cli.services.file_cache.file_cache_service import FileCacheService
from aws_idr_customer_cli.utils.attachment_splitter import split_json_for_attachments
from aws_idr_customer_cli.utils.constants import CommandType
from aws_idr_customer_cli.utils.context import is_integration_test_mode
from aws_idr_customer_cli.utils.feature_flags import (
    SUPPORT_CASE_KEY,
    Feature,
    FeatureFlags,
    Stage,
)
from aws_idr_customer_cli.utils.log_handlers import CliLogger


class SupportCaseService:
    """Support Case functionality creation"""

    @inject
    def __init__(
        self,
        accessor: SupportCaseAccessor,
        file_cache_service: FileCacheService,
        logger: CliLogger,
    ) -> None:
        self.accessor = accessor
        self.file_cache_service = file_cache_service
        self.logger = logger
        self._additional_attachment_sets: list[str] = []

    def create_case(self, session_id: str) -> str:
        """Create a support case for workload onboarding.

        Args:
            session_id: Session ID for the workload

        Returns:
            str: The created support case ID
        """
        # Check if support case creation feature is enabled
        if not FeatureFlags.is_enabled_for_stage(Feature.MVP, Stage.DEV):
            self.logger.error("Support case creation feature is not enabled")
            raise ValueError("Support case creation feature is not available")

        # Get file path to determine command type
        file_path = self.file_cache_service.get_file_path(session_id)
        complete_data = self.file_cache_service.load_file_cache(file_path=file_path)

        if not complete_data:
            self.logger.error("No submission data found")
            raise ValueError("Submission data not found")

        # Only validate workload onboarding for workload registration
        if complete_data.progress.workload_registration:
            if not self.file_cache_service.validate_workload_onboarding():
                self.logger.error("Workload onboarding data is invalid")
                raise ValueError("Workload onboarding data is invalid")

        # Get workload data from loaded submission
        workload_data = complete_data.workload_onboard
        if not workload_data:
            self.logger.error("Workload data not found in submission")
            raise ValueError("Workload data not found")

        # Create the attachment set(s)
        self._additional_attachment_sets = []
        attachment_set_id = self._create_json_attachment_set(file_path)

        # Create the case with first attachment set
        case_id = self._create_case_with_attachment(workload_data, attachment_set_id)

        # Add additional attachment sets as communications (if any)
        # Retry decorator on add_communication_to_case handles rate limiting
        for idx, additional_set_id in enumerate(
            self._additional_attachment_sets or [], start=2
        ):
            self.accessor.add_communication_to_case(
                case_id, f"Additional workload data (part {idx})", additional_set_id
            )

        return case_id

    def describe_case(self, case_id: str) -> Dict[str, Any]:
        """Describe a support case by case ID."""
        cases = self.accessor.describe_cases(case_id_list=[case_id])
        if not cases:
            raise SupportCaseNotFoundError(f"Case {case_id} not found")
        case_detail: Dict[str, Any] = cases[0]
        return case_detail

    @staticmethod
    def _get_command_type_from_submission(submission: OnboardingSubmission) -> str:
        """Get command type from submission progress tracker."""
        if submission.progress.alarm_creation:
            command_type = CommandType.ALARM_CREATION.value
        elif submission.progress.alarm_ingestion:
            command_type = CommandType.ALARM_INGESTION.value
        elif submission.progress.apm_setup:
            command_type = CommandType.APM_SETUP.value
        else:
            command_type = CommandType.WORKLOAD_REGISTRATION.value
        return str(command_type)

    def _create_json_attachment_set(self, file_path: Path) -> str:
        """Create JSON attachment set with complete workload data.

        Returns the first attachment set ID. Additional attachment set IDs
        are stored in self._additional_attachment_sets for later use.
        """
        # Get complete data from file cache (this gets the OnboardingSubmission object)
        complete_data = self.file_cache_service.load_file_cache(file_path=file_path)
        if not complete_data:
            self.logger.error("No complete data found in file cache")
            raise ValueError("Complete data not found in cache")

        json_content = complete_data.to_json(indent=2, ensure_ascii=False)

        # Get command type from submission progress tracker
        command_type = self._get_command_type_from_submission(complete_data)

        # Split attachments if size exceeds 5MB (5120 KB)
        attachments = split_json_for_attachments(
            json_content, command_type=command_type
        )

        if not attachments:
            raise ValueError("Failed to create attachments from JSON content")

        if len(attachments) > 1:
            self.logger.info(
                f"JSON size exceeds 5MB, split into {len(attachments)} parts"
            )

        # Create attachment sets (max 3 attachments per set)
        attachment_set_ids = []
        for i in range(0, len(attachments), 3):
            batch = attachments[i : i + 3]
            attachment_set_id = self.accessor.add_attachments_to_set(batch)
            if not attachment_set_id:
                raise ValueError(
                    f"Failed to create attachment set for batch {i//3 + 1}"
                )
            attachment_set_ids.append(attachment_set_id)
            self.logger.info(f"Attachment set {i//3 + 1} created: {attachment_set_id}")

        # Store additional attachment sets for later (after case creation)
        self._additional_attachment_sets = (
            attachment_set_ids[1:] if len(attachment_set_ids) > 1 else []
        )

        # Return first attachment set ID (for case creation)
        return attachment_set_ids[0] if attachment_set_ids else ""

    def _create_case_with_attachment(
        self,
        workload_data: WorkloadOnboard,
        attachment_set_id: str,
    ) -> str:
        """Create support case with pre-created JSON attachment set"""
        workload_name = workload_data.name
        if not workload_name:
            self.logger.error("Workload name is empty")
            raise ValueError("Workload name cannot be empty")

        subject = f"AWS Incident Detection and Response - {workload_name}"
        existing_case_id = self.get_duplicate_case_id(subject)
        if existing_case_id:
            self.logger.info(
                f"A support case for workload '{workload_name}' already exists.\n"
                f"The case ID is {existing_case_id}. A new support case will not be created.\n"
                "Visit the AWS Support Center link to view or update the existing case.\n"
                f"https://console.aws.amazon.com/support/home#/case/?displayId={existing_case_id}\n"
            )
            raise SupportCaseAlreadyExistsError(
                f"❌ A support case for workload '{workload_name}' already exists \n"
                f"with case ID: {existing_case_id}. Please visit the AWS Support Center\n"
                "to view or update the existing case instead of creating a new one. \n"
            )

        communication_body = f"""Hello,

        Please onboard the following workload for AWS IDR services:

        Workload Name: {workload_name}

        Note: This request is created by AWS IDR CLI tool on behalf of customer.

        Thanks"""

        # Get configuration values from feature flags
        severity = self._get_severity()
        category = self._get_category()
        issue_type = self._get_issue_type()
        language = self._get_language()
        service_code = self._get_service_code()

        self.logger.info(f"Creating support case with subject: {subject}")

        case_id: str = self.accessor.create_support_case(
            subject=subject,
            severity=severity,
            category=category,
            communicationBody=communication_body,
            issueType=issue_type,
            attachmentSetId=attachment_set_id,
            language=language,
            serviceCode=service_code,
        )
        return case_id

    def get_duplicate_case_id(self, subject: str) -> str:
        """Check if a case with the given subject already exists and return its case ID"""
        cases = self.accessor.describe_cases(include_resolved_cases=False)
        for case in cases:
            if case.get("subject") == subject:
                case_id = case.get("caseId", "")
                self.logger.debug(
                    f"Found existing case with subject '{subject}' "
                    f"and case ID: {case_id}"
                )
                return str(case_id)
        return ""

    def is_case_resolved(self, case_id: str) -> bool:
        """Check if a support case is resolved/closed.

        Args:
            case_id: The AWS Support case ID to check.

        Returns:
            True if the case status is 'resolved', False otherwise.
        """
        try:
            case_details = self.describe_case(case_id)
            status = str(case_details.get("status", "")).lower()
            return status == "resolved"
        except Exception as e:
            self.logger.warning(f"Could not check case status for {case_id}: {e}")
            return False  # Safe default to avoid blocking workflow

    def update_case_with_attachment_set(
        self, session_id: str, case_id: str
    ) -> Optional[str]:
        """Update existing support case with new attachment set.

        Args:
            session_id: Session ID for the workload
            case_id: The AWS Support case ID to update.

        Returns:
            The case_id if update was successful, None if case is resolved/closed
            (indicating caller should create a new case instead).

        Raises:
            ValueError: If case_id is empty or invalid
            AlarmIngestionValidationError: If alarm ingestion data is invalid
            AlarmCreationValidationError: If alarm creation data is invalid
        """
        if not case_id or not case_id.strip():
            self.logger.error("Case ID is required for update")
            raise ValueError("Case ID cannot be empty")

        # Check if case is resolved - if so, return None to signal caller to create new case
        if self.is_case_resolved(case_id):
            self.logger.info(
                f"Case {case_id} is resolved. Returning None to signal new case needed."
            )
            return None

        # Determine command type from progress tracker
        file_cache = self.file_cache_service.file_cache
        if file_cache.progress.alarm_creation:
            if not self.file_cache_service.is_alarm_creation_data_valid():
                self.logger.error("Alarm creation data is invalid")
                raise AlarmCreationValidationError("Alarm creation data is invalid")
        elif file_cache.progress.alarm_ingestion:
            if not self.file_cache_service.is_alarm_ingestion_data_valid():
                self.logger.error("Alarm ingestion data is invalid")
                raise AlarmIngestionValidationError("Alarm ingestion data is invalid")
        elif file_cache.progress.workload_registration:
            # Workload registration - no additional validation needed
            self.logger.info("Processing workload registration support case update")
        else:
            self.logger.error("Unknown command type")
            raise ValueError("Cannot determine command type from progress tracker")

        file_path = self.file_cache_service.get_file_path(session_id)
        try:
            # Get attachment set id
            self._additional_attachment_sets = []
            attachment_set_id = self._create_json_attachment_set(file_path=file_path)
            message = "Updated attachment with alarm information"
            self.accessor.add_communication_to_case(
                case_id,
                message,
                attachment_set_id,
            )
            self.logger.info(f"Case {case_id} updated successfully with new attachment")

            # Add additional attachment sets as communications (if any)
            # Retry decorator on add_communication_to_case handles rate limiting
            for idx, additional_set_id in enumerate(
                self._additional_attachment_sets or [], start=2
            ):
                self.accessor.add_communication_to_case(
                    case_id, f"Additional alarm data (part {idx})", additional_set_id
                )
        except Exception as e:
            self.logger.error(f"Error updating case {case_id}: {str(e)}")
            raise

        return case_id

    def _get_effective_stage(self) -> Stage:
        """Get the effective stage for feature configuration lookup.

        Returns:
            Stage.DEV if in integration test mode, otherwise the normal stage
        """
        if is_integration_test_mode():
            return Stage.DEV
        return FeatureFlags.get_stage(Feature.MVP)

    def _get_support_case_config(self) -> Dict[str, str]:
        """Get support case configuration for the effective stage.

        Returns:
            Configuration dictionary for support case fields
        """
        effective_stage = self._get_effective_stage()
        feature_configs = FeatureFlags._FEATURE_CONFIGS.get(Feature.MVP, {})
        stage_config = feature_configs.get(effective_stage, {})
        config = stage_config.get(SUPPORT_CASE_KEY, {})

        return cast(Dict[str, str], config)

    def _get_severity(self) -> str:
        """Get severity value from feature flags using effective stage."""
        config = self._get_support_case_config()
        severity = cast(str, config["severity"])
        self.logger.info(f"Using support case severity: '{severity}'")
        return severity

    def _get_category(self) -> str:
        """Get category value from feature flags using effective stage."""
        config = self._get_support_case_config()
        category = cast(str, config["category"])
        self.logger.info(f"Using support case category: '{category}'")
        return category

    def _get_issue_type(self) -> str:
        """Get issue type value from feature flags using effective stage."""
        config = self._get_support_case_config()
        issue_type = cast(str, config["issue_type"])
        self.logger.info(f"Using support case issue_type: '{issue_type}'")
        return issue_type

    def _get_language(self) -> str:
        """Get language value from feature flags using effective stage."""
        config = self._get_support_case_config()
        language = cast(str, config["language"])
        self.logger.info(f"Using support case language: '{language}'")
        return language

    def _get_service_code(self) -> str:
        """Get service code value from feature flags using effective stage.

        Returns:
            Service code for support case routing
        """
        config = self._get_support_case_config()
        service_code = cast(str, config["service_code"])
        self.logger.info(f"Using support case service_code: '{service_code}'")
        return service_code
