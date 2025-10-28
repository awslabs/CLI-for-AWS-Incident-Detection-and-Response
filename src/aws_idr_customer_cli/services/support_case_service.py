from pathlib import Path
from typing import Any, Dict, cast

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
from aws_idr_customer_cli.services.file_cache.data import WorkloadOnboard
from aws_idr_customer_cli.services.file_cache.file_cache_service import FileCacheService
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

        # Validate information for workload onboarding
        if not self.file_cache_service.validate_workload_onboarding():
            self.logger.error("Workload onboarding data is invalid")
            raise ValueError("Workload onboarding data is invalid")

        # Get workload data from file cache
        workload_data = self.file_cache_service.get_workload_onboarding()

        # Create the attachment set
        file_path = self.file_cache_service.get_file_path(session_id)
        attachment_set_id = self._create_json_attachment_set(file_path)

        # Create the case with attachment set
        case_id = self._create_case_with_attachment(workload_data, attachment_set_id)
        return case_id

    def describe_case(self, case_id: str) -> Dict[str, Any]:
        """Describe a support case by case ID."""
        cases = self.accessor.describe_cases(case_id_list=[case_id])
        if not cases:
            raise SupportCaseNotFoundError(f"Case {case_id} not found")
        case_detail: Dict[str, Any] = cases[0]
        return case_detail

    def _create_json_attachment_set(self, file_path: Path) -> str:
        """Create JSON attachment set with complete workload data"""
        # Get complete data from file cache (this gets the OnboardingSubmission object)
        complete_data = self.file_cache_service.load_file_cache(file_path=file_path)
        if not complete_data:
            self.logger.error("No complete data found in file cache")
            raise ValueError("Complete data not found in cache")

        json_content = complete_data.to_json(indent=2, ensure_ascii=False)
        attachments = [
            {"fileName": "workload_configuration.json", "data": json_content}
        ]

        attachment_set_id: str = self.accessor.add_attachments_to_set(attachments)

        if not attachment_set_id:
            raise ValueError("Failed to create attachment set")

        self.logger.info(f"JSON attachment set created: {attachment_set_id}")
        return attachment_set_id

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

    def update_case_with_attachment_set(self, session_id: str, case_id: str) -> None:
        """Update existing support case with new attachment set
        Args:
            session_id: Session ID for the workload
            case_id: The AWS Support case ID to update.
        Raises:
            ValueError: If case_id is empty or invalid
            AlarmIngestionValidationError: If alarm ingestion data is invalid
            AlarmCreationValidationError: If alarm creation data is invalid
        """
        if not case_id or not case_id.strip():
            self.logger.error("Case ID is required for update")
            raise ValueError("Case ID cannot be empty")

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
            attachment_set_id = self._create_json_attachment_set(file_path=file_path)
            message = "Updated attachment with alarm information"
            self.accessor.add_communication_to_case(
                case_id,
                message,
                attachment_set_id,
            )
            self.logger.info(f"Case {case_id} updated successfully with new attachment")
        except Exception as e:
            self.logger.error(f"Error updating case {case_id}: {str(e)}")
            raise

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
