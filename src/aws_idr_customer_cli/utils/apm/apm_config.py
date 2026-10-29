"""APM configuration utility functions."""

from typing import List, Optional, cast

from aws_idr_customer_cli.utils.apm.apm_constants import (
    APM_PROVIDERS,
    EVENTBRIDGE_INSTRUCTIONS,
    FALLBACK_INSTRUCTION,
    GENERATE_ONLY_FORMAT_DEFAULT,
    GENERATE_ONLY_FORMAT_YAML,
    GENERATE_ONLY_TEMPLATE_FILENAME_PATTERN,
    GENERATE_ONLY_TEMPLATE_FILENAME_PATTERN_YAML,
    INTEGRATION_PARAMETERS,
    PROVIDER_TEMPLATE_FILES,
    SNS_INSTRUCTIONS,
    TEMPLATE_FILES,
    WEBHOOK_INSTRUCTIONS,
    ApmProvider,
    ApmProviderConfig,
    IntegrationType,
)


def resolve_provider_enum(apm_provider: str) -> Optional[ApmProvider]:
    """Resolve a provider name string to its ApmProvider enum, or None."""
    for provider in ApmProvider:
        if provider.value == apm_provider:
            return provider
    return None


def get_provider_config(apm_provider: str) -> ApmProviderConfig:
    """
    Get complete configuration for APM provider.

    Args:
        apm_provider: Name of the APM provider (string)

    Returns:
        Complete provider configuration

    Raises:
        ValueError: If provider is not supported
    """
    provider_enum = resolve_provider_enum(apm_provider)

    if provider_enum is None or provider_enum not in APM_PROVIDERS:
        supported = ", ".join([p.value for p in ApmProvider])
        raise ValueError(
            f"Unsupported APM provider: '{apm_provider}'. "
            f"Supported providers: {supported}"
        )

    return APM_PROVIDERS[provider_enum]


def get_integration_type(apm_provider: str) -> IntegrationType:
    """Get integration type for APM provider."""
    return get_provider_config(apm_provider).integration_type


def get_default_incident_path(apm_provider: str) -> str:
    """Get default incident detection path for APM provider."""
    return str(get_provider_config(apm_provider).incident_path.path)


def get_template_file(apm_provider: str) -> str:
    """Get CloudFormation template file for APM provider."""
    config = get_provider_config(apm_provider)
    # Check provider-level override first
    provider_enum = resolve_provider_enum(apm_provider)
    if provider_enum and provider_enum in PROVIDER_TEMPLATE_FILES:
        return str(PROVIDER_TEMPLATE_FILES[provider_enum])
    return str(TEMPLATE_FILES[config.integration_type])


def get_required_parameters(integration_type: IntegrationType) -> List[str]:
    """Get required parameters for integration type."""
    return list(INTEGRATION_PARAMETERS[integration_type])


def get_all_provider_names() -> List[str]:
    """
    Get list of all supported provider names for UI display.

    Returns:
        List of provider names as strings
    """
    return [str(provider.value) for provider in ApmProvider]


def get_provider_domains(apm_provider: str) -> List[str]:
    """Get validation domains for APM provider."""
    return list(get_provider_config(apm_provider).domains)


def get_setup_instructions(provider: str) -> List[str]:
    """Get setup instructions for APM provider prerequisites."""
    try:
        config = get_provider_config(provider)
        integration_type = config.integration_type

        if integration_type == IntegrationType.SAAS:
            return [
                str(instruction.format(provider=provider))
                for instruction in EVENTBRIDGE_INSTRUCTIONS
            ]
        elif integration_type == IntegrationType.SNS:
            return [
                str(instruction.format(provider=provider))
                for instruction in SNS_INSTRUCTIONS
            ]
        elif integration_type == IntegrationType.NON_SAAS:
            return list(WEBHOOK_INSTRUCTIONS)
        else:
            return [str(FALLBACK_INSTRUCTION.format(provider=provider))]
    except ValueError:
        return [str(FALLBACK_INSTRUCTION.format(provider=provider))]


def get_integration_type_description(integration_type: IntegrationType) -> str:
    """Get user-friendly description for integration type."""
    descriptions = {
        IntegrationType.SAAS: "EventBridge Integration (SAAS)",
        IntegrationType.SNS: "SNS Topic Integration",
        IntegrationType.NON_SAAS: "Webhook Integration (NON_SAAS)",
    }
    return cast(str, descriptions.get(integration_type, integration_type.value))


def generate_stack_name(apm_provider: str) -> str:
    """
    Generate CloudFormation stack name following naming convention.

    Args:
        apm_provider: Name of the APM provider

    Returns:
        Formatted stack name (e.g., "Datadog-IntegrationForIDR")
    """
    # Validate provider exists
    get_provider_config(apm_provider)
    clean_apm_name = apm_provider.replace(" ", "")
    return f"{clean_apm_name}-IntegrationForIDR"


def get_default_generate_only_template_path(
    apm_provider: str, output_format: str = GENERATE_ONLY_FORMAT_DEFAULT
) -> str:
    """Build the default output path for a generate-only template export.

    Args:
        apm_provider: Name of the APM provider
        output_format: "json" (default) or "yaml" — selects the file extension

    Returns:
        Relative default path (e.g., "awsidr-apm-Datadog-template.json"
        or "awsidr-apm-Datadog-template.yaml")
    """
    clean_apm_name = apm_provider.replace(" ", "")
    if output_format == GENERATE_ONLY_FORMAT_YAML:
        pattern = GENERATE_ONLY_TEMPLATE_FILENAME_PATTERN_YAML
    else:
        pattern = GENERATE_ONLY_TEMPLATE_FILENAME_PATTERN
    return str(pattern.format(provider=clean_apm_name))


def get_lambda_function_name(apm_provider: str) -> str:
    """Generate Lambda function name from provider.

    Args:
        apm_provider: Name of the APM provider

    Returns:
        Lambda function name (e.g., "DataDog-AWSIncidentDetectionResponse-Lambda-Transform")
    """
    clean_provider = apm_provider.replace(" ", "")
    return f"{clean_provider}-AWSIncidentDetectionResponse-Lambda-Transform"
