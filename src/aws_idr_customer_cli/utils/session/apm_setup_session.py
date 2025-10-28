from typing import Any, Dict, List, Optional

from botocore.exceptions import ClientError

from aws_idr_customer_cli.clients.iam import BotoIamManager
from aws_idr_customer_cli.services.apm.apm_service import ApmService
from aws_idr_customer_cli.services.file_cache.data import ApmSetup
from aws_idr_customer_cli.services.file_cache.file_cache_service import FileCacheService
from aws_idr_customer_cli.services.support_case_service import SupportCaseService
from aws_idr_customer_cli.utils.apm.apm_config import (
    generate_stack_name,
    get_all_provider_names,
    get_default_incident_path,
    get_integration_type,
    get_integration_type_description,
    get_lambda_function_name,
)
from aws_idr_customer_cli.utils.apm.apm_constants import (
    APM_CUSTOM_INCIDENT_PATH_INPUT_MESSAGE,
    APM_CUSTOM_INCIDENT_PATH_MESSAGE,
    APM_DEPLOYMENT_COMPLETE_MESSAGE,
    APM_NEXT_STEPS_COMMAND,
    APM_NEXT_STEPS_INSTRUCTIONS,
    APM_PROVIDER_SELECTED_MESSAGE,
    APM_PROVIDER_SELECTION_MESSAGE,
    APM_REGION_SELECTED_MESSAGE,
    APM_REGION_SELECTION_MESSAGE,
    APM_STEP_CHECK_EXISTING_STACK,
    APM_STEP_DEPLOY_STACK,
    APM_STEP_INCIDENT_PATH,
    APM_STEP_INTEGRATION_READY,
    APM_STEP_NEXT_STEPS,
    APM_STEP_PREREQUISITES,
    APM_STEP_REVIEW_CONFIGURATION,
    APM_STEP_SELECT_PROVIDER,
    APM_STEP_SELECT_REGION,
    APM_TEST_MANUAL_VALIDATION_STEPS,
    APM_TEST_MESSAGES,
    APM_VALIDATION_CANCELLED_MESSAGE,
    APM_VALIDATION_EXTENDED_WAIT_CANCELLED,
    APM_VALIDATION_EXTENDED_WAIT_OPTION,
    APM_VALIDATION_EXTENDED_WAIT_PROMPT,
    APM_VALIDATION_EXTENDED_WAIT_START,
    APM_VALIDATION_EXTENDED_WAIT_TIMEOUT,
    APM_VALIDATION_MANUAL_STEPS,
    APM_WEBHOOK_CONFIGURATION_HEADER,
    APM_WEBHOOK_CREDENTIALS_HEADER,
    APM_WEBHOOK_INSTRUCTIONS_HEADER,
    APM_WEBHOOK_PAUSE_MESSAGE,
    APM_WEBHOOK_RESUME_MESSAGE,
    APM_WEBHOOK_SECRET_KEY_LABEL,
    APM_WEBHOOK_SETUP_INSTRUCTIONS,
    APM_WEBHOOK_TOKEN_LABEL,
    APM_WEBHOOK_URL_LABEL,
    APM_WEBHOOK_VALIDATION_NOTE,
    CONFIG_MODIFY_APM_PROVIDER,
    CONFIG_MODIFY_DEPLOYMENT_REGION,
    SESSION_STEP_INDEX_NEXT_STEPS,
    SESSION_STEP_INDEX_SELECT_PROVIDER,
    SESSION_STEP_INDEX_SELECT_REGION,
    VALIDATION_EXTENDED_WAIT_MINUTES,
    VALIDATION_POLL_INTERVAL,
    ApmDocumentationUrls,
    IntegrationType,
    ValidationStatus,
)
from aws_idr_customer_cli.utils.apm.apm_stack_helpers import extract_stack_resources
from aws_idr_customer_cli.utils.constants import DEFAULT_REGION, CommandType
from aws_idr_customer_cli.utils.session.interactive_session import (
    ACTION_BACK,
    ACTION_KEY,
    ACTION_QUIT,
    STYLE_BLUE,
    STYLE_DIM,
    InteractiveSession,
    session_step,
)
from aws_idr_customer_cli.utils.session.session_store import SessionStore
from aws_idr_customer_cli.utils.validation.apm_validation import (
    ApmPrerequisiteValidator,
    validate_aws_region,
)


class ApmSetupSession(InteractiveSession):
    """APM setup session for integrating APM providers with IDR."""

    def __init__(
        self,
        store: SessionStore,
        apm_service: ApmService,
        file_cache_service: FileCacheService,
        support_case_service: SupportCaseService,
        iam_manager: BotoIamManager,
        apm_validator: ApmPrerequisiteValidator,
        account_id: str = "123456789012",
        resume_session_id: Optional[str] = None,
    ) -> None:
        """Initialize APM setup session following working command patterns."""
        super().__init__(CommandType.APM_SETUP, account_id, store, resume_session_id)

        self.apm_service = apm_service
        self.file_cache_service = file_cache_service
        self.support_case_service = support_case_service
        self.iam_manager = iam_manager
        self.apm_validator = apm_validator

    def _display_resume_info(self) -> None:
        """Display information about resuming APM setup session."""
        if not self.submission:
            return

        self.ui.display_info("📋 Resuming APM setup session...")

        if self.submission.workload_onboard:
            self._display_workload_context()

        if self.submission.apm_setup:
            self._display_apm_context()

    def _display_workload_context(self) -> None:
        """Display existing workload information context."""
        workload = self.submission.workload_onboard
        if not workload:
            return

        self.ui.display_info("🏢 Existing Workload Information:", style=STYLE_BLUE)
        self.ui.display_info(f"  • Name: {workload.name}", style=STYLE_DIM)
        self.ui.display_info(
            f"  • Enterprise: {workload.enterprise_name}", style=STYLE_DIM
        )
        self.ui.display_info(
            f"  • Regions: {', '.join(workload.regions)}", style=STYLE_DIM
        )

        if workload.support_case_id:
            self.ui.display_info(
                f"  • Existing Support Case: {workload.support_case_id}",
                style=STYLE_DIM,
            )

    def _display_apm_context(self) -> None:
        """Display existing APM setup context."""
        apm = self.submission.apm_setup
        if not apm:
            return

        self.ui.display_info("🔧 APM Setup Progress:", style=STYLE_BLUE)

        if apm.provider:
            self.ui.display_info(f"  • Provider: {apm.provider}", style=STYLE_DIM)

        integration_arn = apm.partner_event_source_arn or apm.sns_topic_arn
        if integration_arn:
            self.ui.display_info(
                f"  • Integration ARN: {integration_arn}", style=STYLE_DIM
            )

        if apm.resources:
            self.ui.display_info(
                f"  • Resources Created: {len(apm.resources)} items",
                style=STYLE_DIM,
            )

    def _initialize_apm_setup(self) -> None:
        """Initialize APM setup data structure if needed."""
        if not self.submission.apm_setup:
            self.submission.apm_setup = ApmSetup(provider="", deployment_region="")

    def _require_provider(self) -> bool:
        """Check if provider is selected. Returns True if valid, False otherwise."""
        if not self.submission.apm_setup.provider:
            self.ui.display_error("No APM provider selected.")
            return False
        return True

    def _navigate_to_step(self, step: int) -> Dict[str, Any]:
        """Navigate back to a specific step."""
        self.current_step = step
        self._save_progress()
        return {ACTION_KEY: ACTION_BACK}

    @session_step(APM_STEP_SELECT_REGION, order=1)
    def _select_deployment_region(self) -> Dict[str, Any]:
        """Select region for APM infrastructure deployment."""
        self._initialize_apm_setup()

        workload = self.submission.workload_onboard
        if workload and workload.regions:
            selected_region = self._select_from_workload_regions(workload.regions)
        else:
            selected_region = self._prompt_for_region()

        self.submission.apm_setup.deployment_region = selected_region
        self._save_progress()

        self.ui.display_info(APM_REGION_SELECTED_MESSAGE.format(region=selected_region))
        return {}

    def _select_from_workload_regions(self, regions: List[str]) -> str:
        """Select region from available workload regions."""
        self.ui.display_info("🌍 APM Integration Infra Deployment Region")
        self.ui.display_info(f"Available workload regions: {', '.join(regions)}")

        region_index = self.ui.select_option(regions, APM_REGION_SELECTION_MESSAGE)
        return str(regions[region_index])

    def _prompt_for_region(self) -> str:
        """Prompt user for region with validation."""
        self.ui.display_info("🌍 APM Integration Infra Deployment Region")

        while True:
            region = self.ui.prompt_input(
                "Enter region for APM deployment", default=DEFAULT_REGION
            )
            input_region = region.strip() or DEFAULT_REGION

            try:
                validated_region = validate_aws_region(
                    input_region, self.apm_validator.base_validator
                )
                return str(validated_region)
            except Exception as e:
                self.ui.display_error(f"Invalid region '{input_region}': {str(e)}")
                self.ui.display_info(
                    "Please enter a valid AWS region (e.g., us-east-1, eu-west-1)"
                )

    @session_step(APM_STEP_SELECT_PROVIDER, order=2)
    def _select_apm_provider(self) -> Dict[str, Any]:
        """Select APM provider for integration."""
        providers = get_all_provider_names()
        provider_index = self.ui.select_option(
            providers, APM_PROVIDER_SELECTION_MESSAGE
        )
        selected_provider = providers[provider_index]

        self.ui.display_info(
            APM_PROVIDER_SELECTED_MESSAGE.format(provider=selected_provider)
        )

        self.submission.apm_setup.provider = selected_provider
        self._save_progress()

        return {}

    @session_step(APM_STEP_REVIEW_CONFIGURATION, order=3)
    def _review_apm_configuration(self) -> Dict[str, Any]:
        """Review and confirm APM configuration before proceeding."""
        apm_setup = self.submission.apm_setup
        integration_type = get_integration_type(apm_setup.provider)

        self.ui.display_result(
            "📋  APM Configuration Review",
            {
                "Deployment Region": apm_setup.deployment_region,
                "APM Provider": apm_setup.provider,
                "Integration Type": get_integration_type_description(integration_type),
            },
        )

        if self.ui.prompt_confirm(
            "Would you like to proceed with this APM configuration?", default=True
        ):
            self.ui.display_info("✅  APM configuration confirmed for integration")
            return {}

        return self._handle_configuration_modification()

    def _handle_configuration_modification(self) -> Dict[str, Any]:
        """Handle user request to modify configuration."""
        options = ["Deployment Region", "APM Provider", "Cancel modification"]
        choice = self.ui.select_option(options, "What would you like to modify?")

        step_map = {
            CONFIG_MODIFY_DEPLOYMENT_REGION: SESSION_STEP_INDEX_SELECT_REGION,
            CONFIG_MODIFY_APM_PROVIDER: SESSION_STEP_INDEX_SELECT_PROVIDER,
        }

        if choice in step_map:
            return self._navigate_to_step(step_map[choice])

        self.ui.display_info("✅ APM configuration confirmed")
        return {}

    @session_step(APM_STEP_CHECK_EXISTING_STACK, order=4)
    def _check_existing_stack(self) -> Dict[str, Any]:
        """Check for existing CloudFormation stack for the selected APM provider."""
        apm_setup = self.submission.apm_setup
        provider = apm_setup.provider
        region = apm_setup.deployment_region or DEFAULT_REGION

        if not self._require_provider():
            return {ACTION_KEY: ACTION_BACK}

        stack_name = generate_stack_name(provider)
        self.ui.display_info(
            f"🔍 Checking for existing {provider} CloudFormation stack..."
        )

        stack_exists = self.apm_service.cloudformation_accessor.stack_exists(
            stack_name=stack_name, region=region, exclude_deleted=True
        )

        if stack_exists:
            self.ui.display_info(f"✅ Found existing {provider} stack: {stack_name}")
            self.ui.display_info(
                "📋 APM Integration Infrastructure stack is already present in your account, "
                f"(please proceed with ingesting APM alarms using {APM_NEXT_STEPS_COMMAND} command)"
            )
            return self._navigate_to_step(SESSION_STEP_INDEX_NEXT_STEPS)
        else:
            self.ui.display_info(
                f"ℹ️  No existing {provider} stack found. Proceeding with new deployment."
            )

        return {}

    @session_step(APM_STEP_PREREQUISITES, order=5)
    def _validate_prerequisites(self) -> Dict[str, Any]:
        """Validate provider-specific prerequisites using interactive validator methods."""
        apm_setup = self.submission.apm_setup
        provider = apm_setup.provider
        region = apm_setup.deployment_region or DEFAULT_REGION

        if not self._require_provider():
            return {ACTION_KEY: ACTION_BACK}

        integration_type = get_integration_type(provider)

        validator_map = {
            IntegrationType.SAAS: lambda: self.apm_validator.validate_saas_prerequisites(
                provider, region, self.ui, self.submission
            ),
            IntegrationType.SNS: lambda: self.apm_validator.validate_sns_prerequisites(
                provider, region, self.ui, self.submission
            ),
            IntegrationType.NON_SAAS: lambda: self.apm_validator.validate_non_saas_prerequisites(
                provider, self.ui
            ),
        }

        validator = validator_map.get(integration_type)
        if not validator:
            return {}

        result = validator()
        if result == {}:
            self._save_progress()

        return dict(result)

    @session_step(APM_STEP_INCIDENT_PATH, order=6)
    def _configure_incident_detection_path(self) -> Dict[str, Any]:
        """Configure incident detection response identifier path."""
        provider = self.submission.apm_setup.provider

        if not self._require_provider():
            return {ACTION_KEY: ACTION_BACK}

        default_path = get_default_incident_path(provider)

        use_custom = self.ui.prompt_confirm(
            f"{APM_CUSTOM_INCIDENT_PATH_MESSAGE.format(provider=provider)} "
            f"({provider} by default uses: {default_path})",
            default=False,
        )

        if use_custom:
            custom_path = self.ui.prompt_input(APM_CUSTOM_INCIDENT_PATH_INPUT_MESSAGE)
            self.ui.display_info(f"✅ Using custom path: {custom_path}")
            self.submission.apm_setup.custom_incident_path = custom_path
        else:
            self.ui.display_info(f"✅ Using default path: {default_path}")
            self.submission.apm_setup.custom_incident_path = None

        self._save_progress()
        return {}

    @session_step(APM_STEP_DEPLOY_STACK, order=7)
    def _deploy_cloudformation_stack(self) -> Dict[str, Any]:
        """Deploy CloudFormation stack for APM integration."""
        apm_setup = self.submission.apm_setup
        provider = apm_setup.provider
        region = apm_setup.deployment_region or DEFAULT_REGION
        integration_type = get_integration_type(provider)

        if not self._require_provider():
            return {ACTION_KEY: ACTION_BACK}
        # Check if stack already exists and resources are stored (resuming after webhook config)
        stack_name = generate_stack_name(provider)
        if (
            apm_setup.resources
            and self.apm_service.cloudformation_accessor.stack_exists(
                stack_name=stack_name, region=region, exclude_deleted=True
            )
        ):
            self.ui.display_info(f"✅ Stack {stack_name} already deployed")
            # For NON_SAAS, if we're resuming after webhook config, skip to next step
            if integration_type == IntegrationType.NON_SAAS:
                self.ui.display_info("ℹ️  Proceeding to validation step...")
                return {}
            return {}

        if not self._confirm_deployment(provider, region):
            self.ui.display_info(
                f"Deployment cancelled. Run this command again "
                f"when you're ready to deploy AWS resources in {region}."
            )
            return {ACTION_KEY: ACTION_QUIT}

        integration_type = get_integration_type(provider)

        try:
            if integration_type == IntegrationType.NON_SAAS:
                result = self.apm_service.deploy_non_saas_stack(
                    provider, region, apm_setup.custom_incident_path
                )
            else:
                incident_path = (
                    apm_setup.custom_incident_path
                    or get_default_incident_path(provider)
                )
                parameters = self.apm_service.build_cfn_parameters(
                    provider, integration_type, apm_setup
                )
                self._display_cfn_parameters(
                    provider.replace(" ", ""), parameters, incident_path
                )

                result = self.apm_service.deploy_saas_or_sns_stack(
                    provider,
                    region,
                    integration_type,
                    apm_setup,
                    apm_setup.custom_incident_path,
                )

            if not result.get("success", False):
                self.ui.display_info(
                    f"   • Resume after fixing: awsidr setup-apm --resume {self.session_id}"
                )
                return {ACTION_KEY: ACTION_QUIT}

            if integration_type == IntegrationType.NON_SAAS:
                self.ui.display_info(APM_DEPLOYMENT_COMPLETE_MESSAGE)
                # For NON_SAAS, display webhook configuration and pause session
                apm_setup.resources = result
                self._save_progress()
                return self._display_webhook_configuration_and_pause(provider, region)

            apm_setup.resources = result
            self._save_progress()

        except ClientError as e:
            self.ui.display_error(f"Deployment error: {e}")
            self.ui.display_info(
                f"   • Resume after fixing: awsidr setup-apm --resume {self.session_id}"
            )
            return {ACTION_KEY: ACTION_QUIT}
        return {}

    def _confirm_deployment(self, provider: str, region: str) -> bool:
        """Confirm CloudFormation stack deployment with user."""
        stack_name = generate_stack_name(provider)
        self.ui.display_info("📋 CloudFormation Deployment Summary")
        self.ui.display_info(f"  • Stack Name: {stack_name}")
        self.ui.display_info(f"  • Region: {region}")
        self.ui.display_info(f"  • Provider: {provider}")

        result = self.ui.prompt_confirm(
            "⚠️  This will create AWS resources. Proceed with deployment?", default=True
        )
        return bool(result)

    def _display_cfn_parameters(
        self, clean_provider_name: str, parameters: Dict[str, str], incident_path: str
    ) -> None:
        """Display CloudFormation parameters for confirmation."""
        self.ui.display_info(f"📋 CloudFormation Parameters for {clean_provider_name}:")
        for key, value in parameters.items():
            self.ui.display_info(f"  • {key}: {value}")
        self.ui.display_info(f"  • Incident Path: {incident_path}")

    @session_step(APM_STEP_INTEGRATION_READY, order=8)
    def _check_apm_lambda_integration(self) -> Dict[str, Any]:
        """Validate APM events in transformation Lambda logs."""
        provider = self.submission.apm_setup.provider
        region = self.submission.apm_setup.deployment_region or DEFAULT_REGION
        integration_type = get_integration_type(provider)
        lambda_name = get_lambda_function_name(provider)

        self._display_integration_message(integration_type, "context")

        validation_result = self.apm_service.validate_lambda_logs(provider, region)
        status = validation_result.status

        if status == ValidationStatus.SUCCESS:
            self.ui.display_info(f"✅ {validation_result.message}")
            self._display_integration_message(integration_type, "description")
            return {}

        if status == ValidationStatus.SKIPPED:
            self.ui.display_info(validation_result.message)
            self._display_manual_validation_steps(lambda_name)
            return {}

        if status == ValidationStatus.CANCELLED:
            self.ui.display_warning(APM_VALIDATION_CANCELLED_MESSAGE)
            self._display_manual_validation_steps(lambda_name)
            return {}

        if status == ValidationStatus.TIMEOUT:
            self.ui.display_warning(f"⚠️  {validation_result.message}")
            return self._handle_no_lambda_activity(provider, region)

        # ERROR or unknown status
        self.ui.display_error(f"❌ {validation_result.message}")
        self._display_manual_validation_steps(lambda_name)
        return {}

    def _handle_no_lambda_activity(self, provider: str, region: str) -> Dict[str, Any]:
        """Handle case when no Lambda activity detected - offer extended wait."""
        lambda_name = get_lambda_function_name(provider)

        self.ui.display_info(
            APM_VALIDATION_EXTENDED_WAIT_OPTION.format(VALIDATION_EXTENDED_WAIT_MINUTES)
        )

        if not self.ui.prompt_confirm(
            APM_VALIDATION_EXTENDED_WAIT_PROMPT.format(
                VALIDATION_EXTENDED_WAIT_MINUTES
            ),
            default=True,
        ):
            self._display_manual_validation_steps(lambda_name)
            return {}

        return self._extended_wait_for_lambda_activity(
            provider, region, lambda_name, max_minutes=VALIDATION_EXTENDED_WAIT_MINUTES
        )

    def _extended_wait_for_lambda_activity(
        self, provider: str, region: str, lambda_name: str, max_minutes: int
    ) -> Dict[str, Any]:
        """Wait for Lambda activity - continuous wait with checks every minute."""
        self.ui.display_info(APM_VALIDATION_EXTENDED_WAIT_START.format(max_minutes))

        max_wait_seconds = max_minutes * 60
        validation_result = self.apm_service.validate_lambda_logs(
            provider,
            region,
            lookback_minutes=max_minutes,
            limit=10,
            max_wait_seconds=max_wait_seconds,
            skip_prompt=True,
            poll_interval=VALIDATION_POLL_INTERVAL,
        )

        status = validation_result.status

        if status == ValidationStatus.SUCCESS:
            self.ui.display_info(f"\n✅ {validation_result.message}")
            integration_type = get_integration_type(provider)
            self._display_integration_message(integration_type, "description")
            return {}

        if status == ValidationStatus.CANCELLED:
            self.ui.display_warning(APM_VALIDATION_EXTENDED_WAIT_CANCELLED)
        else:
            self.ui.display_warning(
                APM_VALIDATION_EXTENDED_WAIT_TIMEOUT.format(max_minutes)
            )
        self._display_manual_validation_steps(lambda_name)
        return {}

    def _display_integration_message(
        self, integration_type: IntegrationType, message_key: str
    ) -> None:
        """Display integration-specific message by type and key."""
        message = APM_TEST_MESSAGES.get(integration_type, {}).get(message_key)
        if message:
            self.ui.display_info(message)

    def _display_manual_validation_steps(self, lambda_name: str) -> None:
        """Display manual validation steps for the user."""
        self.ui.display_info(
            APM_TEST_MANUAL_VALIDATION_STEPS.format(function_name=lambda_name)
        )
        self.ui.display_info(APM_VALIDATION_MANUAL_STEPS)

    @session_step(APM_STEP_NEXT_STEPS, order=9)
    def _display_next_steps(self) -> Dict[str, Any]:
        """Display next steps for ingesting APM alerts into IDR."""
        eventbus_arn = getattr(self.submission.apm_setup, "eventbus_arn", None)

        if not eventbus_arn:
            provider = self.submission.apm_setup.provider
            region = self.submission.apm_setup.deployment_region or DEFAULT_REGION
            stack_name = generate_stack_name(provider)
            resources = extract_stack_resources(
                stack_name=stack_name,
                region=region,
                account_id=self.account_id,
                cloudformation_accessor=self.apm_service.cloudformation_accessor,
            )
            eventbus_arn = resources["eventbus_arn"]

            if not eventbus_arn:
                self.ui.display_warning(
                    "Could not automatically extract EventBus ARN from stack resources. "
                    "Please retrieve it manually from the AWS Console"
                )

        for line in APM_NEXT_STEPS_INSTRUCTIONS:
            self.ui.display_info(line)

        if eventbus_arn:
            self.ui.display_info(f"   • Custom EventBus ARN: {eventbus_arn}")
        else:
            self.ui.display_info("   • Custom EventBus ARN: ")

        return {}

    def _display_webhook_configuration_and_pause(
        self, provider: str, region: str
    ) -> Dict[str, Any]:
        """Display webhook configuration instructions and pause session for NON_SAAS."""
        stack_name = generate_stack_name(provider)

        # Extract all resources in one call
        resources = extract_stack_resources(
            stack_name=stack_name,
            region=region,
            account_id=self.account_id,
            cloudformation_accessor=self.apm_service.cloudformation_accessor,
        )

        if not resources["webhook_url"] or not resources["secret_name"]:
            self.ui.display_warning(
                "⚠️  Could not extract all webhook configuration details. "
                "Please retrieve them from AWS Console (CloudFormation → Stack → Resources). "
            )

        self.ui.display_info(APM_WEBHOOK_CONFIGURATION_HEADER.format(provider=provider))
        self.ui.display_info(APM_WEBHOOK_PAUSE_MESSAGE.format(provider=provider))
        self.ui.display_info(APM_WEBHOOK_CREDENTIALS_HEADER)

        if resources["webhook_url"]:
            self.ui.display_info(f"\n{APM_WEBHOOK_URL_LABEL}")
            self.ui.display_info(f"  {resources['webhook_url']}")

        if resources["secret_name"]:
            self.ui.display_info(f"\n{APM_WEBHOOK_TOKEN_LABEL}")
            self.ui.display_info(f"  • Secret Name: {resources['secret_name']}")
            self.ui.display_info(
                f"  • Retrieve from: AWS Secrets Manager → "
                f"{resources['secret_name']} → Retrieve secret value"
            )
            self.ui.display_info(APM_WEBHOOK_SECRET_KEY_LABEL)

        self.ui.display_info(APM_WEBHOOK_INSTRUCTIONS_HEADER)
        self._display_provider_specific_instructions(
            resources["webhook_url"], resources["secret_name"]
        )

        doc_url = ApmDocumentationUrls.get_provider_docs(provider)
        self.ui.display_info(f"\n📖 Documentation: {doc_url}")

        self.ui.display_info(
            APM_WEBHOOK_RESUME_MESSAGE.format(session_id=self.session_id)
        )
        self.ui.display_info(APM_WEBHOOK_VALIDATION_NOTE)

        if resources["eventbus_arn"]:
            self.submission.apm_setup.eventbus_arn = resources["eventbus_arn"]

        self._save_progress()

        return {ACTION_KEY: ACTION_QUIT}

    def _display_provider_specific_instructions(
        self, webhook_url: Optional[str], secret_name: Optional[str]
    ) -> None:
        """Display provider-specific webhook configuration instructions."""
        for line in APM_WEBHOOK_SETUP_INSTRUCTIONS:
            self.ui.display_info(line)
            if "3. Create a new webhook notification:" in line:
                if webhook_url:
                    self.ui.display_info(f"     • URL: {webhook_url}")
                if secret_name:
                    self.ui.display_info("     • Add HTTP Header: authorizationToken")
                    self.ui.display_info(
                        "     • Header Value: [Token from Secrets Manager]"
                    )
