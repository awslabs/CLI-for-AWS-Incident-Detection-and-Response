import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable, Dict, Optional

from arnparse import arnparse

from aws_idr_customer_cli.core.interactive.ui import InteractiveUI
from aws_idr_customer_cli.data_accessors.eventbridge_accessor import EventBridgeAccessor
from aws_idr_customer_cli.data_accessors.sns_accessor import SnsAccessor
from aws_idr_customer_cli.exceptions import ValidationError
from aws_idr_customer_cli.services.file_cache.data import OnboardingSubmission
from aws_idr_customer_cli.utils.apm.apm_config import (
    get_all_provider_names,
    get_provider_domains,
)
from aws_idr_customer_cli.utils.apm.apm_constants import (
    APM_EVENTBRIDGE_PREREQUISITE_MESSAGE,
    APM_PARTNER_EVENT_SOURCE_INPUT_MESSAGE,
    APM_SNS_PREREQUISITE_MESSAGE,
    APM_SNS_TOPIC_INPUT_MESSAGE,
    APM_VALIDATION_SUCCESS_MESSAGE,
    ApmDocumentationUrls,
)
from aws_idr_customer_cli.utils.arn_utils import extract_account_id_from_arn
from aws_idr_customer_cli.utils.session.interactive_session import (
    ACTION_KEY,
    ACTION_QUIT,
)
from aws_idr_customer_cli.utils.validation.validator import Validate

# Constants
SNS_TOPIC_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
EVENTBRIDGE_PARTNER_BUS_PATTERN = re.compile(r"^aws\.partner/[^/]+/.+$")
DEFAULT_MAX_RETRIES = 1


@dataclass
class ValidationResult:
    """Structured validation result."""

    is_valid: bool
    value: Optional[str] = None
    error_message: Optional[str] = None
    help_url: Optional[str] = None


@lru_cache(maxsize=1)
def _get_cached_provider_data() -> Dict[str, list]:
    """Cache expensive provider domain lookups."""
    provider_data = {}
    for provider in get_all_provider_names():
        try:
            provider_data[provider] = get_provider_domains(provider)
        except ValueError:
            continue
    return provider_data


def _validate_string_input(value: str, field_name: str) -> str:
    """Validate and clean string input."""
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be text")

    clean_value = value.strip()
    if not clean_value:
        raise ValidationError(f"{field_name} cannot be empty")

    return clean_value


def validate_aws_region(region: str, validator: Validate) -> str:
    """Validate AWS region format and existence."""
    if not region:
        raise ValidationError("Region cannot be empty")

    validated_region = Validate.required(region.strip())
    return str(validator.aws_region(validated_region))


def validate_sns_arn_format(arn: str) -> str:
    """Validate SNS topic ARN format only."""
    clean_arn = _validate_string_input(arn, "SNS topic ARN")

    try:
        parsed_arn = arnparse(clean_arn)
        extract_account_id_from_arn(clean_arn)

        if parsed_arn.service != "sns":
            raise ValidationError(
                f"Invalid SNS ARN. Expected service 'sns', got '{parsed_arn.service}'"
            )

        if not SNS_TOPIC_PATTERN.match(parsed_arn.resource):
            raise ValidationError(
                "SNS topic name must contain only letters, numbers, hyphens, and underscores"
            )

    except ValidationError:
        raise
    except (KeyError, AttributeError, IndexError) as e:
        raise ValidationError(f"Invalid SNS topic ARN format: {str(e)}")
    except Exception as e:
        raise ValidationError(f"Unexpected error validating SNS topic ARN: {str(e)}")

    return clean_arn


def validate_sns_topic_exists(
    arn: str, region: str, validator: Validate, sns_accessor: SnsAccessor
) -> str:
    """Validate SNS topic ARN format and existence."""
    validated_arn = validate_sns_arn_format(arn)
    validated_region = validate_aws_region(region, validator)

    try:
        sns_accessor.get_topic_attributes(validated_region, validated_arn)
    except PermissionError:
        raise ValidationError(
            f"Unable to access SNS topic '{validated_arn}' in region '{validated_region}'. "
            "Please ensure your AWS credentials have sns:GetTopicAttributes permission."
        )
    except ValueError:
        topic_name = validated_arn.split(":")[-1]
        raise ValidationError(
            f"SNS topic '{topic_name}' was not found in region '{validated_region}'. "
            "Please create it at: https://console.aws.amazon.com/sns/"
        )

    return validated_arn


def validate_eventbridge_partner_bus_format(bus_name: str, selected_apm: str) -> str:
    """Validate Partner Event Bus name format and provider match."""
    clean_name = _validate_string_input(bus_name, "Partner Event Bus name")

    if not EVENTBRIDGE_PARTNER_BUS_PATTERN.match(clean_name):
        raise ValidationError(
            f"The Partner Event Bus name '{clean_name}' doesn't match the expected format. "
            f"Expected format: aws.partner/<provider_domain>/<bus_identifier> "
            f"(e.g., aws.partner/datadog.com/my-bus or aws.partner/newrelic.com/123456/my-bus)"
        )

    # Validate that the bus name contains a supported provider domain
    _validate_apm_provider_domain(clean_name, "Partner Event Bus")

    # Validate that the detected provider matches the selected APM provider
    provider_data = _get_cached_provider_data()

    if selected_apm not in provider_data:
        raise ValidationError(
            f"Unsupported APM provider: {selected_apm}. "
            f"Supported providers: {', '.join(provider_data.keys())}"
        )

    detected_provider = find_provider_by_domain(clean_name)

    if detected_provider != selected_apm:
        expected_domains = provider_data[selected_apm]
        if detected_provider:
            raise ValidationError(
                f"Event bus mismatch: You selected '{selected_apm}' but "
                f"provided an event bus for '{detected_provider}'. Please provide "
                "an event bus that matches your selected APM provider."
            )
        else:
            raise ValidationError(
                f"Event bus mismatch: The provided event bus does not "
                f"match the selected APM provider '{selected_apm}'. "
                f"Expected domains: {', '.join(expected_domains)}"
            )

    return clean_name


def validate_eventbridge_partner_bus_exists(
    bus_name: str,
    region: str,
    selected_apm: str,
    validator: Validate,
    eventbridge_accessor: EventBridgeAccessor,
) -> str:
    """Validate Partner Event Bus name format and existence."""
    validated_name = validate_eventbridge_partner_bus_format(bus_name, selected_apm)
    validated_region = validate_aws_region(region, validator)

    try:
        eventbridge_accessor.describe_event_bus(validated_region, validated_name)
    except PermissionError:
        raise ValidationError(
            f"Unable to access Partner Event Bus "
            f"'{validated_name}' in region '{validated_region}'. "
            "Please ensure your AWS credentials have events:DescribeEventBus permission."
        )
    except ValueError:
        raise ValidationError(
            f"Partner Event Bus '{validated_name}'"
            f" was not found in region '{validated_region}'. "
            "Please set up the partner event source first in your APM provider console, "
            "then associate it with EventBridge."
        )

    return validated_name


def find_provider_by_domain(value: str) -> Optional[str]:
    """Find which APM provider a value belongs to based on domain."""
    value_lower = value.lower()
    provider_data = _get_cached_provider_data()

    for provider, domains in provider_data.items():
        if any(f"/{domain}/" in value_lower for domain in domains):
            return provider

    return None


def _validate_apm_provider_domain(value: str, context: str = "resource") -> str:
    """Internal helper to validate APM provider domain requirement."""
    if find_provider_by_domain(value):
        return value

    provider_data = _get_cached_provider_data()
    all_domains = [domain for domains in provider_data.values() for domain in domains]

    raise ValidationError(
        f"{context} must contain a supported APM provider domain. "
        f"Supported: {', '.join(all_domains)}"
    )


def validate_eventbridge_bus_matches_apm_provider(
    event_bus_name: str, selected_apm: str
) -> str:
    """Validate that the event bus name matches the selected APM provider."""
    validated_bus = validate_eventbridge_partner_bus_format(
        event_bus_name, selected_apm
    )
    provider_data = _get_cached_provider_data()

    if selected_apm not in provider_data:
        raise ValidationError(
            f"Unsupported APM provider: {selected_apm}. "
            f"Supported providers: {', '.join(provider_data.keys())}"
        )

    detected_provider = find_provider_by_domain(validated_bus)

    if detected_provider == selected_apm:
        return validated_bus

    expected_domains = provider_data[selected_apm]

    if detected_provider:
        raise ValidationError(
            f"Event bus mismatch: You selected '{selected_apm}' but "
            f"provided an event bus for '{detected_provider}'. Please provide "
            "an event bus that matches your selected APM provider."
        )
    else:
        raise ValidationError(
            f"Event bus mismatch: The provided event bus does not "
            f"match the selected APM provider '{selected_apm}'. "
            f"Expected domains: {', '.join(expected_domains)}"
        )


class ApmPrerequisiteValidator:
    """Comprehensive APM prerequisite validation for setup-apm command."""

    def __init__(
        self,
        base_validator: Validate,
        eventbridge_accessor: Optional[EventBridgeAccessor] = None,
        sns_accessor: Optional[SnsAccessor] = None,
    ):
        self.base_validator = base_validator
        self.eventbridge_accessor = eventbridge_accessor
        self.sns_accessor = sns_accessor

    def _handle_validation_with_retry(
        self,
        ui: InteractiveUI,
        validation_func: Callable[[], ValidationResult],
        success_callback: Callable[[str], None],
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> Dict[str, Any]:
        """Generic retry handler for validation operations."""
        for attempt in range(max_retries + 1):
            result = validation_func()

            if result.is_valid and result.value is not None:
                success_callback(result.value)
                ui.display_info(APM_VALIDATION_SUCCESS_MESSAGE)
                return {}

            ui.display_error(f"Validation failed: {result.error_message}")
            if result.help_url:
                ui.display_info(f"Documentation: {result.help_url}")

            if attempt < max_retries:
                ui.display_info(
                    f"Please try again ({attempt + 1}/{max_retries + 1} attempts)"
                )
            else:
                ui.display_error("Maximum retry attempts reached.")
                return {ACTION_KEY: ACTION_QUIT}

        return {ACTION_KEY: ACTION_QUIT}

    def _get_example_event_bus_arn(self, provider: str) -> str:
        """Generate example EventBridge partner event bus ARN for a provider."""
        provider_data = _get_cached_provider_data()
        domain = provider_data.get(provider, ["provider.com"])[0]
        return f"aws.partner/{domain}/123456789012/source_name"

    def validate_sns_topic(self, sns_arn: str, region: str) -> ValidationResult:
        """Validate SNS topic - returns structured result."""
        try:
            if self.sns_accessor:
                validated_arn = validate_sns_topic_exists(
                    sns_arn, region, self.base_validator, self.sns_accessor
                )
            else:
                validated_arn = validate_sns_arn_format(sns_arn)

            return ValidationResult(is_valid=True, value=validated_arn)

        except ValidationError as e:
            return ValidationResult(
                is_valid=False,
                error_message=str(e),
                help_url=ApmDocumentationUrls.EVENTBRIDGE,
            )

    def validate_partner_event_source(
        self, event_bus_name: str, region: str, provider: str
    ) -> ValidationResult:
        """Validate EventBridge partner event source format and existence."""
        try:
            if self.eventbridge_accessor:
                validated_bus = validate_eventbridge_partner_bus_exists(
                    event_bus_name,
                    region,
                    provider,
                    self.base_validator,
                    self.eventbridge_accessor,
                )
            else:
                validated_bus = validate_eventbridge_bus_matches_apm_provider(
                    event_bus_name, provider
                )

            return ValidationResult(is_valid=True, value=validated_bus)

        except ValidationError as e:
            return ValidationResult(
                is_valid=False,
                error_message=str(e),
                help_url=ApmDocumentationUrls.EVENTBRIDGE,
            )

    def validate_saas_prerequisites(
        self,
        provider: str,
        region: str,
        ui: InteractiveUI,
        submission: OnboardingSubmission,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> Dict[str, Any]:
        """Handle SAAS prerequisite validation with retry logic and UI interaction."""
        example_arn = self._get_example_event_bus_arn(provider)

        if not ui.prompt_confirm(
            f"{APM_EVENTBRIDGE_PREREQUISITE_MESSAGE.format(provider=provider)} "
            f"(example: {example_arn})",
            default=True,
        ):
            ui.display_error(f" Patner EventBridge setup required for {provider}.")
            ui.display_info(f"Documentation: {ApmDocumentationUrls.EVENTBRIDGE}")
            return {ACTION_KEY: ACTION_QUIT}

        def validation_func() -> ValidationResult:
            user_input = ui.prompt_input(
                APM_PARTNER_EVENT_SOURCE_INPUT_MESSAGE.format(provider=provider)
            )
            return self.validate_partner_event_source(user_input, region, provider)

        def success_callback(validated_value: str) -> None:
            submission.apm_setup.partner_event_source_arn = validated_value

        return self._handle_validation_with_retry(
            ui, validation_func, success_callback, max_retries
        )

    def validate_sns_prerequisites(
        self,
        provider: str,
        region: str,
        ui: InteractiveUI,
        submission: OnboardingSubmission,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> Dict[str, Any]:
        """Handle SNS prerequisite validation with retry logic and UI interaction."""
        if not ui.prompt_confirm(
            f"{APM_SNS_PREREQUISITE_MESSAGE.format(provider=provider)} "
            "(example: arn:aws:sns:eu-west-1:012345678912:grafana-sns)",
            default=True,
        ):
            ui.display_error(f"SNS setup required for {provider}.")
            ui.display_info(
                f"Documentation: {ApmDocumentationUrls.get_provider_docs(provider)}"
            )
            return {ACTION_KEY: ACTION_QUIT}

        def validation_func() -> ValidationResult:
            user_input = ui.prompt_input(APM_SNS_TOPIC_INPUT_MESSAGE)
            return self.validate_sns_topic(user_input, region)

        def success_callback(validated_value: str) -> None:
            submission.apm_setup.sns_topic_arn = validated_value

        return self._handle_validation_with_retry(
            ui, validation_func, success_callback, max_retries
        )

    def validate_non_saas_prerequisites(
        self, provider: str, ui: InteractiveUI
    ) -> Dict[str, Any]:
        """Handle Non-SAAS prerequisite validation with UI interaction.
        TODO: Update logic to handle non saas in a different way for webhook based integration
        """
        ui.display_info(f"🔧 {provider} Integration Setup")
        ui.display_info(
            f"{provider} uses webhook integration to send events to AWS account."
        )
        ui.display_info(
            "We'll deploy a CloudFormation stack to create the necessary AWS resources "
            "for webhook integration."
        )
        return {}
