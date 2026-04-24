"""APM-specific constants and configurations."""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List


class ValidationStatus(str, Enum):
    """Lambda validation status types."""

    SUCCESS = "success"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    ERROR = "error"


class IntegrationType(str, Enum):
    """APM integration types."""

    SAAS = "SAAS_INTEGRATION"
    SNS = "SNS_INTEGRATION"
    NON_SAAS = "NON_SAAS"


class ApmProvider(str, Enum):
    """Supported APM providers."""

    DATADOG = "Datadog"
    NEW_RELIC = "New Relic"
    GRAFANA_CLOUD = "Grafana Cloud"
    SPLUNK = "Splunk Observability Cloud"
    DYNATRACE = "Dynatrace"
    GRAFANA_OSS = "Grafana OSS"
    PAGERDUTY = "PagerDuty"


@dataclass(frozen=True)
class IncidentPath:
    """Structured incident detection path configuration."""

    path: str


@dataclass(frozen=True)
class ApmProviderConfig:
    """Configuration for an APM provider."""

    integration_type: IntegrationType
    incident_path: IncidentPath
    domains: List[str]


# ============================================================================
# SERVICE LAYER CONSTANTS (Used by apm_service.py)
# ============================================================================

# CloudFormation Parameters
PARAM_APM_NAME = "APMNameParameter"
PARAM_EVENT_BUS_NAME = "PartnerEventBusNameParameter"
PARAM_EVENT_BUS_PREFIX = "PartnerEventBusPrefixParameter"
PARAM_SNS_TRIGGER = "TriggerSNSParameter"

# CloudFormation Status
CFN_DELETED_STATUS = "DELETE_COMPLETE"
CFN_FAILED_STATUS = "FAILED"

# Template Configuration
TEMPLATE_ENCODING = "utf-8"

# Service Error Messages
ERROR_TEMPLATE_NOT_FOUND = "Template not found: {}"
ERROR_TEMPLATE_EMPTY = "Template {} is empty"
ERROR_TEMPLATE_LOAD_FAILED = "Failed to load template resource: {}"
ERROR_TEMPLATE_FAILED = "Template loading failed for {}: {}"
ERROR_PARTNER_ARN_MISSING = "Partner Event Source ARN not configured"
ERROR_SNS_ARN_MISSING = "SNS Topic ARN not configured"

# Service Display Messages
MSG_DEPLOYMENT_FAILED = "CloudFormation deployment failed"
MSG_ROLLBACK_INITIATED = "🔄 Automatically rolling back stack..."
MSG_ROLLBACK_COMPLETE = "✅ Stack rollback completed."
MSG_ROLLBACK_FAILED = "⚠️ Rollback failed: {}"
MSG_NO_RESOURCES = "📋 No resources to display"

# Resource Type Labels for Display
RESOURCE_TYPE_LABELS: Dict[str, str] = {
    "Lambda": "Function",
    "Events": "EventBridge",
    "EventBridge": "EventBridge",
    "ApiGateway": "API Gateway",
    "SecretsManager": "Secrets Manager",  # pragma: allowlist secret
}

# Failure Guidance Patterns
FAILURE_GUIDANCE: Dict[str, List[str]] = {
    "Parameter validation failed": [
        "   • Verify your parameter values are correct",
        "   • Check ARN formats and resource existence",
    ],
    "Access|Permission": [
        "   • Verify your AWS credentials have sufficient permissions",
        "   • Check IAM policies for CloudFormation and related services",
    ],
    "already exists": [
        "   • A resource with the same name already exists",
        "   • Try again or clean up existing resources",
    ],
}

DEFAULT_FAILURE_GUIDANCE: List[str] = [
    "   • Review the failure reason above",
    "   • Check AWS CloudFormation console for detailed error logs",
    "   • CloudFormation Console: {cfn_console_url}",
    "   • Look for stack: {stack_name}",
    "   • Try the deployment again by resuming the session",
]

# ============================================================================
# SESSION/UI LAYER CONSTANTS (Used by apm_setup_session.py)
# ============================================================================

# APM Step Names
APM_STEP_SELECT_REGION = "Select Deployment Region"
APM_STEP_SELECT_PROVIDER = "Select APM Provider"
APM_STEP_REVIEW_CONFIGURATION = "Review APM Setup Configuration"
APM_STEP_CHECK_EXISTING_STACK = "Check Existing Stack"
APM_STEP_PREREQUISITES = "Integration Prerequisites"
APM_STEP_INCIDENT_PATH = "Configure Incident Detection Event Path"
APM_STEP_DEPLOY_STACK = "Deploy CloudFormation Stack"
APM_STEP_INTEGRATION_READY = "Validate APM Integration Readiness"
APM_STEP_NEXT_STEPS = "Ingest APM Alarms"

# APM UI Messages
APM_REGION_PROMPT = "Enter region for apm integration infra deployment"
APM_REGION_SELECTION_MESSAGE = "Select region for APM deployment"
APM_PROVIDER_SELECTION_MESSAGE = "Select your APM provider"
APM_PREREQUISITE_CHECK_MESSAGE = "Checking APM integration prerequisites"
APM_DEPLOYMENT_SUCCESS_MESSAGE = "APM infrastructure setup complete"
APM_NEXT_STEPS_COMMAND = "awsidr ingest-alarms"

# APM Validation Messages
APM_EVENTBRIDGE_PREREQUISITE_MESSAGE = (
    "Do you have a Partner Event Source setup in Amazon EventBridge for {provider}?"
)
APM_SNS_PREREQUISITE_MESSAGE = (
    "Do you have an SNS Topic setup in AWS "
    "SNS console that receives events from {provider}?"
)
APM_PARTNER_EVENT_SOURCE_INPUT_MESSAGE = (
    "Enter partner event source name for {provider}"
)
APM_SNS_TOPIC_INPUT_MESSAGE = (
    "Enter the SNS Topic ARN that receives events from your APM"
)
APM_CUSTOM_INCIDENT_PATH_MESSAGE = (
    "Do you have any custom incident detection event path for {provider}?"
)
APM_CUSTOM_INCIDENT_PATH_INPUT_MESSAGE = (
    "Enter your custom incident detection event path"
)

# APM Success Messages
APM_VALIDATION_SUCCESS_MESSAGE = "✅ Validation successful"
APM_REGION_SELECTED_MESSAGE = "✅ Selected region: {region}"
APM_PROVIDER_SELECTED_MESSAGE = "✅ Selected: {provider}"
APM_DEPLOYMENT_COMPLETE_MESSAGE = "✅ CloudFormation deployment completed successfully!"

# APM Testing Messages (new)
APM_TEST_INTEGRATION_MESSAGE = (
    "Would you like to test the APM integration? "
    "(Note: You must have active alarms configured in your APM that trigger events)"
)
APM_TEST_SKIP_MESSAGE = (
    "⏭️  Skipping integration test - you can test anytime using the instructions below"
)
APM_TEST_LAMBDA_VALIDATION_MESSAGE = (
    "Would you like to validate that events are being processed by the Lambda function?"
)
APM_TEST_WEBHOOK_CONFIGURED_MESSAGE = (
    "Have you configured and tested the webhook in your {provider} console?"
)
APM_TEST_EVENTS_DETECTED_MESSAGE = (
    "Do you see recent successful invocations in the Lambda metrics?"
)
APM_TEST_SUCCESS_MESSAGE = "Integration test successful - events are being processed!"
APM_TEST_NO_EVENTS_MESSAGE = (
    "ℹ️  No events detected in the last 90 seconds.\n"
    "\nPossible reasons:\n"
    "  • No alarms have triggered yet in the APM (normal for new setups)\n"
    "  • Alert thresholds not breached\n"
    "  • Events may take 5-7 minutes to appear depending on APM\n"
    "\nTo test: Trigger an alert in your APM or wait for a natural alert to occur."
)

APM_TEST_WAITING = "⏳  Waiting for Lambda activity (up to {} seconds)..."
APM_TEST_CHECKING = "⏱️  Waiting for activity..."
APM_TEST_CANCELLED = "Validation cancelled."
APM_TEST_ERROR = (
    "Failed to retrieve Lambda logs: {}. Please verify logs manually in CloudWatch."
)

# APM Testing Instructions (based on official docs)
APM_TEST_MANUAL_VALIDATION_STEPS = (
    "\n💡 Manual Validation:\n"
    "   1. Send a test alert from your APM (if you haven't already)\n"
    "   2. Navigate to: AWS Lambda → {function_name} → Monitor\n"
    "   3. Check for successful invocations in metric graphs\n"
    "   4. Select 'View CloudWatch Logs' to check log streams\n"
    "   5. Look for 'Received payload' entries and verify no errors"
)

# Validation session messages
APM_VALIDATION_CANCELLED_MESSAGE = "Validation cancelled by user"

APM_VALIDATION_EXTENDED_WAIT_OPTION = (
    "\n⏰ Extended Wait Option:\n"
    "   • We can wait up to {} minutes, checking every minute\n"
    "   • During this time, send a test alert from your APM\n"
    "   • You can stop waiting at any time by pressing Ctrl+C"
)
APM_VALIDATION_EXTENDED_WAIT_PROMPT = (
    "Would you like to wait up to {} minutes for Lambda to receive events?"
)
APM_VALIDATION_EXTENDED_WAIT_START = "\n⏳ Starting extended wait (up to {} minutes)..."

APM_VALIDATION_EXTENDED_WAIT_CANCELLED = " Extended wait cancelled by user"
APM_VALIDATION_EXTENDED_WAIT_TIMEOUT = "No Lambda activity detected after {} minutes"
APM_VALIDATION_MANUAL_STEPS = (
    "\n💡 For more details, please refer:\n"
    "https://w.amazon.com/bin/view/Mixtape/Third_Party_APM_CloudFormation_Stack"
)

# Integration-specific testing messages
APM_TEST_MESSAGES: Dict[IntegrationType, Dict[str, str]] = {
    IntegrationType.SAAS: {
        "context": "🔍 Optional: Check if EventBridge events are reaching Lambda",
        "description": "This validates that your Partner Event Source is sending events.",
    },
    IntegrationType.SNS: {
        "context": "🔍 Optional: Check if SNS events are reaching Lambda",
        "description": "This validates that your SNS topic is sending events.",
    },
    IntegrationType.NON_SAAS: {
        "context": "🔍 Optional: Check if webhook events are reaching Lambda",
        "description": "This validates that your webhook configuration is working.",
    },
}

# Webhook configuration messages
APM_WEBHOOK_CONFIGURATION_HEADER = "\n🔗 {provider} Webhook Configuration Required"
APM_WEBHOOK_PAUSE_MESSAGE = (
    "\n⏸️  Session paused - Please configure the webhook in your {provider} console\n"
)
APM_WEBHOOK_CREDENTIALS_HEADER = "\n📋 AWS Credentials for Webhook Setup:"
APM_WEBHOOK_URL_LABEL = "Webhook URL:"
APM_WEBHOOK_TOKEN_LABEL = "Authentication Token:"
APM_WEBHOOK_INSTRUCTIONS_HEADER = "\n📝 Configuration Steps:"
APM_WEBHOOK_RESUME_MESSAGE = (
    "\n▶️  After configuring the webhook, resume this session:\n"
    "   awsidr setup-apm --resume {session_id}"
)
APM_WEBHOOK_VALIDATION_NOTE = (
    "\nℹ️  Once resumed, we'll validate that events are reaching the Lambda function."
)

# APM Incident path configurations
DEFAULT_INCIDENT_PATHS = {
    ApmProvider.DATADOG: IncidentPath(
        path='event["detail"]["meta"]["monitor"]["name"]'
    ),
    ApmProvider.NEW_RELIC: IncidentPath(path='event["detail"]["workflowName"]'),
    ApmProvider.GRAFANA_CLOUD: IncidentPath(path='alert["labels"]["alertname"]'),
    ApmProvider.SPLUNK: IncidentPath(path='event["detail"]["ruleName"]'),
    ApmProvider.DYNATRACE: IncidentPath(path='raw_json["detail"]["ProblemTitle"]'),
    ApmProvider.GRAFANA_OSS: IncidentPath(path='alert["labels"]["alertname"]'),
    ApmProvider.PAGERDUTY: IncidentPath(
        path='event["detail"]["incident"]["title"]'
    ),
}

# Template file mapping based on integration type
TEMPLATE_FILES: Dict[IntegrationType, str] = {
    IntegrationType.SAAS: "saas_integration.json",
    IntegrationType.SNS: "sns_integration.json",
    IntegrationType.NON_SAAS: "non_saas_integration.json",
}

# Provider-specific template file overrides
PROVIDER_TEMPLATE_FILES: Dict[ApmProvider, str] = {
    ApmProvider.GRAFANA_OSS: "grafana_oss_webhook_integration.json",
}

# Provider-specific Lambda code file overrides
PROVIDER_LAMBDA_CODE_FILES: Dict[ApmProvider, str] = {
    ApmProvider.GRAFANA_OSS: "grafana_oss_lambda.py",
}

# Lambda function code file mapping based on integration type
LAMBDA_CODE_FILES: Dict[IntegrationType, str] = {
    IntegrationType.SAAS: "saas_lambda.py",
    IntegrationType.SNS: "sns_lambda.py",
    IntegrationType.NON_SAAS: "non_saas_lambda.py",
}

# Authorizer Lambda code file mapping based on integration type
AUTHORIZER_CODE_FILES: Dict[IntegrationType, str] = {
    IntegrationType.NON_SAAS: "non_saas_authorizer.js",
}

# Provider-specific authorizer code file overrides
PROVIDER_AUTHORIZER_CODE_FILES: Dict[ApmProvider, str] = {
    ApmProvider.GRAFANA_OSS: "grafana_oss_authorizer.js",
}

# APM Provider configurations
APM_PROVIDERS: Dict[ApmProvider, ApmProviderConfig] = {
    ApmProvider.DATADOG: ApmProviderConfig(
        integration_type=IntegrationType.SAAS,
        incident_path=DEFAULT_INCIDENT_PATHS[ApmProvider.DATADOG],
        domains=["datadog.com", "datadoghq.com"],
    ),
    ApmProvider.NEW_RELIC: ApmProviderConfig(
        integration_type=IntegrationType.SAAS,
        incident_path=DEFAULT_INCIDENT_PATHS[ApmProvider.NEW_RELIC],
        domains=["newrelic.com"],
    ),
    ApmProvider.GRAFANA_CLOUD: ApmProviderConfig(
        integration_type=IntegrationType.SNS,
        incident_path=DEFAULT_INCIDENT_PATHS[ApmProvider.GRAFANA_CLOUD],
        domains=["grafana.com", "grafana.net"],
    ),
    ApmProvider.SPLUNK: ApmProviderConfig(
        integration_type=IntegrationType.SAAS,
        incident_path=DEFAULT_INCIDENT_PATHS[ApmProvider.SPLUNK],
        domains=["splunk.com", "signalfx.com"],
    ),
    ApmProvider.DYNATRACE: ApmProviderConfig(
        integration_type=IntegrationType.NON_SAAS,
        incident_path=DEFAULT_INCIDENT_PATHS[ApmProvider.DYNATRACE],
        domains=["dynatrace.com"],
    ),
    ApmProvider.GRAFANA_OSS: ApmProviderConfig(
        integration_type=IntegrationType.NON_SAAS,
        incident_path=DEFAULT_INCIDENT_PATHS[ApmProvider.GRAFANA_OSS],
        domains=[],
    ),
    ApmProvider.PAGERDUTY: ApmProviderConfig(
        integration_type=IntegrationType.SAAS,
        incident_path=DEFAULT_INCIDENT_PATHS[ApmProvider.PAGERDUTY],
        domains=["pagerduty.com"],
    ),
}

# Parameter definitions for each integration type
INTEGRATION_PARAMETERS: Dict[IntegrationType, List[str]] = {
    IntegrationType.SAAS: [
        "APMNameParameter",
        "PartnerEventBusNameParameter",
        "PartnerEventBusPrefixParameter",
    ],
    IntegrationType.SNS: [
        "APMNameParameter",
        "TriggerSNSParameter",
    ],
    IntegrationType.NON_SAAS: [
        "APMNameParameter",
    ],
}

# Setup instructions for APM prerequisites
EVENTBRIDGE_INSTRUCTIONS = [
    "1. Set up Partner Event Source in {provider} console",
    "2. Associate the Partner Event Source with an " "Event Bus in Amazon EventBridge",
    "3. Note the Partner Event Bus name for APM setup",
    "4. Refer to documentation:"
    " https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-saas.html",
]

SNS_INSTRUCTIONS = [
    "1. Create an SNS topic in AWS SNS console",
    "2. Configure {provider} to send alerts to the SNS topic",
    "3. Note the SNS topic ARN for APM setup",
    "4. Refer to {provider} documentation for SNS integration",
]

WEBHOOK_INSTRUCTIONS = [
    "1. CloudFormation stack will create webhook endpoint",
    "2. After deployment, configure webhook in {provider} console",
    "3. Use the API Gateway endpoint from stack outputs",
]

FALLBACK_INSTRUCTION = "Refer to {provider} documentation for integration setup"

# Stack deployment configuration
STACK_DEPLOYMENT_TIMEOUT = 360
STACK_POLL_INTERVAL = 10


class ApmDocumentationUrls(str, Enum):
    """Documentation URLs for APM integration setup and prerequisites."""

    # AWS EventBridge documentation
    EVENTBRIDGE = (
        "https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-saas.html"
    )

    # APM Provider-specific documentation
    DYNATRACE_WEBHOOK = (
        "https://docs.dynatrace.com/docs/shortlink/problem-notifications#webhook"
    )
    GRAFANA_CLOUD_SNS = (
        "https://grafana.com/docs/grafana/latest/alerting/configure-notifications/"
        "manage-contact-points/integrations/configure-amazon-sns/"
    )
    MANAGED_GRAFANA_SNS = (
        "https://docs.aws.amazon.com/grafana/"
        "latest/userguide/old-alert-notifications.html"
    )

    SPLUNK = (
        "https://help.splunk.com/en/splunk-observability-cloud/manage-data/"
        "available-data-sources/supported-integrations-in-splunk-observability-cloud/"
        "notification-services/send-alerts-to-amazon-eventbridge"
    )

    GRAFANA_OSS_WEBHOOK = (
        "https://grafana.com/docs/grafana/latest/alerting/"
        "configure-notifications/manage-contact-points/"
        "integrations/webhook-notifier/"
    )

    PAGERDUTY_EVENTBRIDGE = (
        "https://support.pagerduty.com/main/docs/amazon-eventbridge-integration-guide"
    )

    @classmethod
    def get_provider_docs(cls, provider: str) -> str:
        """Get documentation URL for specific APM provider."""
        provider_mapping = {
            "Dynatrace": cls.DYNATRACE_WEBHOOK,
            "Grafana Cloud": cls.GRAFANA_CLOUD_SNS,
            "Grafana OSS": cls.GRAFANA_OSS_WEBHOOK,
            "Managed Grafana": cls.MANAGED_GRAFANA_SNS,
            "Splunk Observability Cloud": cls.SPLUNK,
            "PagerDuty": cls.PAGERDUTY_EVENTBRIDGE,
        }
        return provider_mapping.get(provider, cls.EVENTBRIDGE).value


class StackStatus(str, Enum):
    """CloudFormation stack status values."""

    CREATE_COMPLETE = "CREATE_COMPLETE"
    CREATE_FAILED = "CREATE_FAILED"
    ROLLBACK_COMPLETE = "ROLLBACK_COMPLETE"
    ROLLBACK_FAILED = "ROLLBACK_FAILED"
    CREATE_IN_PROGRESS = "CREATE_IN_PROGRESS"
    ROLLBACK_IN_PROGRESS = "ROLLBACK_IN_PROGRESS"
    TIMEOUT = "TIMEOUT"


class StackStatusCategory(Enum):
    """Categories of stack statuses for easier handling."""

    SUCCESS = [StackStatus.CREATE_COMPLETE]
    FAILURE = [
        StackStatus.CREATE_FAILED,
        StackStatus.ROLLBACK_COMPLETE,
        StackStatus.ROLLBACK_FAILED,
    ]
    IN_PROGRESS = [StackStatus.CREATE_IN_PROGRESS, StackStatus.ROLLBACK_IN_PROGRESS]


# APM validation constants
DEFAULT_LOG_LOOKBACK_MINUTES = 10
DEFAULT_LOG_LIMIT = 50
VALIDATION_MAX_WAIT_TIME = 90
VALIDATION_POLL_INTERVAL = 30
VALIDATION_INITIAL_LOOKBACK_MINUTES = 10
VALIDATION_EXTENDED_WAIT_MINUTES = 15

# Session navigation indices
SESSION_STEP_INDEX_SELECT_REGION = 1
SESSION_STEP_INDEX_SELECT_PROVIDER = 2
SESSION_STEP_INDEX_NEXT_STEPS = 9

# Configuration modification options
CONFIG_MODIFY_DEPLOYMENT_REGION = 0
CONFIG_MODIFY_APM_PROVIDER = 1

# APM provider documentation URLs for sending test events
APM_TEST_EVENT_DOCS: Dict[str, str] = {
    "Datadog": "https://docs.datadoghq.com/monitors/notify/#test-notifications",
    "Grafana Cloud": "https://grafana.com/docs/grafana/latest/alerting/"
    "configure-notifications/manage-contact-points/#test-a-contact-point",
    "Splunk": "https://help.splunk.com/en/splunk-observability-cloud/manage-data/"
    "available-data-sources/supported-integrations-in-splunk-observability-cloud/"
    "notification-services/"
    "send-alerts-to-amazon-eventbridge#d87f226acec1d4fbcb7af2061902e1eed__amazoneventbridge",
    "Dynatrace": "https://docs.dynatrace.com/docs/analyze-explore-automate/"
    "notifications-and-alerting/problem-notifications/webhook-integration",
    "New Relic": "https://docs.newrelic.com/docs/alerts/"
    "get-notified/notification-integrations/#eventBridge",
    "Grafana OSS": "https://grafana.com/docs/grafana/latest/alerting/"
    "configure-notifications/manage-contact-points/",
    "PagerDuty": "https://support.pagerduty.com/main/docs/"
    "amazon-eventbridge-integration-guide",
}

# Next steps instructions for alarm ingestion
APM_NEXT_STEPS_INSTRUCTIONS = [
    "Next Steps:",
    "1. Configure your APM tool to send alerts to AWS (if not already done)",
    "2. Run alarm ingestion to onboard APM alarms into IDR:",
    "   awsidr ingest-alarms",
    "3. Provide the following information during alarm ingestion:",
    "   • Alarm identifiers from your APM tool",
]

# Webhook setup instructions for NON_SAAS integrations
APM_WEBHOOK_SETUP_INSTRUCTIONS = [
    "  1. Navigate to your APM console",
    "  2. Go to Settings → Integrations → Webhooks (or similar)",
    "  3. Create a new webhook notification:",
    "  4. Configure the webhook payload (if required)",
    "  5. Test the webhook to verify connectivity",
]

# Grafana OSS-specific webhook setup instructions
GRAFANA_OSS_WEBHOOK_SETUP_INSTRUCTIONS = [
    "  1. Open Grafana → Alerting → Contact points",
    '  2. Click "Add contact point"',
    '  3. Name it (e.g., "IDR Webhook")',
    "  4. Select integration type: Webhook",
    "  5. Set URL to: {webhook_url}",
    '  6. Under "Authorization Header - Scheme": enter Bearer',
    '  7. Under "Authorization Header - Credentials": enter {token_instructions}',
    '  8. Click "Test" to verify, then "Save contact point"',
]

# Grafana documentation version disclaimer
GRAFANA_OSS_DOCS_VERSION_DISCLAIMER = (
    "  ℹ️  Note: Set the Grafana docs version selector to match your "
    "installed Grafana version for the most accurate instructions."
)

# Webhook secret key label
APM_WEBHOOK_SECRET_KEY_LABEL = "  • Key: APMSecureToken"

# APM Error Messages (shared between interactive and non-interactive flows)
IDR_EVENTBRIDGE_NAME_PATTERN = "AWSIncidentDetectionResponse"

EVENTBRIDGE_NAME_VALIDATION_ERROR = (
    f"EventBridge name must contain '{IDR_EVENTBRIDGE_NAME_PATTERN}' "
    "to be part of IDR APM infrastructure. "
    f"Expected format: '<apm-name>-{IDR_EVENTBRIDGE_NAME_PATTERN}-EventBus', "
    "got: '{resource}'. "
    "Ensure the a Custom Event Bus was created using 'awsidr setup-apm'."
)

APM_ALERT_IDENTIFIER_REQUIRED_ERROR = "At least one APM alert identifier is required. "

EVENTBRIDGE_MAX_RETRIES_ERROR = (
    "\n❌ Maximum validation attempts reached.\n\n"
    "Please ensure you have:\n"
    "  1. Completed the APM setup using: awsidr setup-apm\n"
    "  2. Obtained the correct EventBridge event bus ARN\n"
    "  3. Verified the event bus exists in your AWS account\n\n"
    "For setup instructions, visit: "
    "https://w.amazon.com/bin/view/Mixtape/Third_Party_APM_CloudFormation_Stack/"
)

EVENTBRIDGE_NO_BUSES_ERROR = (
    "No eligible EventBridge event buses found in the selected region.\n\n"
    "This could mean:\n"
    "  1. You haven't completed APM setup yet - run: awsidr setup-apm\n"
    "  2. The region selected is incorrect\n\n"
    "Please select a different region or complete APM setup first."
)
