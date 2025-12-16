# Third Party Application Performance Monitoring Setup

The `awsidr setup-apm` command deploys AWS infrastructure to integrate AWS Incident Detection and Response (IDR) with third-party Application Performance Monitoring (APM) tools.

## Supported Integration Types

* **EventBridge (SaaS Partners):** Direct integration via Amazon EventBridge (e.g., Datadog, New Relic, Splunk Observability Cloud). [Learn more](https://docs.aws.amazon.com/IDR/latest/userguide/idr-gs-ingest_alarms_from_apm_to_eventbridge.html)
* **SNS Integration:** Direct integration via Amazon SNS (e.g., Grafana Cloud)
* **Webhook Integration:** API Gateway-based integration for APMs without native AWS support (e.g., Dynatrace)

## Integration Overview

### EventBridge (SaaS Partners)

**For:** Datadog, New Relic, Splunk Observability Cloud

**How it works:** APM tools with native AWS EventBridge support can send alerts directly to a partner event source, which the CLI connects to your custom EventBus.

**Prerequisites:**
* Partner Event Source configured in Amazon EventBridge
* Partner Event Bus name (e.g., `aws.partner/newrelic.com/123456/source_name`)

**Resources Created:**
* Custom EventBus
* EventBridge Rule
* Transform Lambda Function
* IAM Execution Role

For detailed resource information, see [Appendix - APM Integrations](appendix.md#apm-integrations).

**More details:** [Partner Event Source Integration](https://docs.aws.amazon.com/IDR/latest/userguide/idr-gs-ingest_alarms_from_apm_to_eventbridge.html)

### SNS Integration

**For:** Grafana Cloud and APM tools that can publish to Amazon SNS

**How it works:** Your APM publishes alerts to an SNS topic, which the CLI subscribes to with a Lambda function that transforms and routes alerts to IDR.

**Prerequisites:**
* Existing SNS Topic receiving alerts from your APM
* SNS Topic ARN

**Resources Created:**
* Custom EventBus
* SNS Topic Subscription
* Transform Lambda Function
* IAM Execution Role

For detailed resource information, see [Appendix - APM Integrations](appendix.md#apm-integrations).

**More details:** [SNS setup for Grafana Cloud](https://grafana.com/docs/grafana/latest/alerting/configure-notifications/manage-contact-points/integrations/configure-amazon-sns/)

### Webhook Integration (Non-SaaS)

**For:** Dynatrace and APM tools without native AWS integration

**How it works:** The CLI creates an HTTPS webhook endpoint that your APM can call. Requests are authenticated via token and transformed before routing to IDR.

**Prerequisites:**
* None (stack creates all resources)
* APM tool must support HTTPS webhooks with custom headers
* APM tool must be able to send JSON payloads in the required format

**Resources Created:**
* API Gateway REST API with HTTPS endpoint
* Lambda Authorizer (token-based authentication)
* Transform Lambda Function
* Secrets Manager (secure token storage)
* Custom EventBus
* API Gateway Usage Plan with throttling
* IAM Execution Roles

For detailed resource information, see [Appendix - APM Integrations](appendix.md#apm-integrations).

**Post-Deployment Configuration:** After stack deployment, you must configure your APM tool with the following:

* **Webhook URL** (from stack outputs)
  * Important: Use the complete URL including the resource path: `https://{api-id}.execute-api.{region}.amazonaws.com/{stage}/APIGWResourcesforAPM`
* **Authentication Header**
  * Header name: `authorizationToken`
  * Token value: Retrieved from AWS Secrets Manager (provided in stack outputs)
* **Request Format**
  * Method: POST
  * Content-Type: application/json
  * Body structure must include a `detail` object with your alert data

**Testing Your Integration**

Use this curl command template to verify your configuration:

```
curl -X POST https://{your-api-gateway-url}/APIGWResourcesforAPM \
  -H "authorizationToken: {your-token-from-secrets-manager}" \
  -H "Content-Type: application/json" \
  -d '{
    "detail": {
      "ProblemTitle": "Test Alert from APM",
      "State": "OPEN",
      "ProblemID": "TEST-12345",
      "ImpactedEntity": "test-service",
      "Severity": "ERROR"
    }
  }'
```

**Troubleshooting:**
* **403 Error:** Authentication issue - verify your token and header name
* **400 Error:** Authentication successful, but data format issue - check your JSON payload structure includes the detail object
* **404 Error:** Incorrect URL - ensure you're including the full path with /APIGWResourcesforAPM

**More details:** [IDR Webhooks Integration](https://docs.aws.amazon.com/IDR/latest/userguide/idr-ingesting-alarms-using-webhooks.html)

## Deployment Strategy

### Distributed Deployment (Recommended)

Deploy the CloudFormation stack in each workload account and region where APM alerts need to be ingested.

**Example:**

```
Production Server Account (123456789012):
  └─ us-east-1: Deploy stack

Database Account (345678901234):
  └─ us-east-1: Deploy stack
```

### Centralized Deployment

**Important:** Deploying the CloudFormation stack in a single centralized account/region that receives events from all workload accounts is NOT recommended by IDR.

If you must use centralized deployment:
* Include account ID and region in all alarm identifiers:

**Format:** `{AlarmName}_{AccountID}_{Region}`

**Examples:**
```
HighCPU_WebServer_123456789012_us-east-1
DBConnectionPool_345678901234_us-west-2
APILatencyHigh_567890123456_eu-west-1
```

Without this naming convention, IDR may not correctly route incidents or open support cases.

## Validation and Testing

The CLI automatically validates your integration by checking:

**Lambda Invocation Metrics**
* Verifies Transform Lambda is being triggered
* Checks for invocation errors or throttling

**CloudWatch Logs**
* Validates payload is received by Lambda
* Confirms transformation is working correctly

### When Automatic Validation Works

* Your APM has active alerts triggering regularly
* Recent events are available in Partner Event Source or SNS

### Manual Validation

If automatic validation fails or your APM doesn't have active alerts:

1. Send a test alert from your APM tool
2. Navigate to: AWS Lambda → TransformLambdaFunction → Monitor
3. Check for successful invocations in metric graphs
4. Select View CloudWatch Logs to verify:
   * Payload is received
   * No transformation errors

If no errors are found and payload is received successfully, your integration is working.

## CLI Commands

### awsidr setup-apm

**Purpose:** Deploys AWS infrastructure required to set up integration between 3rd party APM providers and AWS account for APM alert event flow.

**What it does:**
* Deploys a CloudFormation stack in your AWS account
* Creates integration bridge between your APM tool and AWS
* Establishes event routing from APM alerts to IDR service

**When to use:** First-time setup or when adding a new APM tool

**Output:**
* Custom EventBus ARN (share with IDR team)
* API Gateway webhook URL (for webhook integrations)
* Secrets Manager token (for webhook integrations)

### awsidr ingest-alarms

**Purpose:** Onboards APM alarms into your IDR workload for incident response

**What it does:**
* Collects workload metadata and associates APM alerts with incident response contacts
* Collects 3rd party alarm information consisting of:
  * Custom EventBus ARN
  * Alarm identifiers
* Creates IDR support case with APM alarm and workload metadata

**When to use:** After setup-apm completes successfully

**Prerequisites:**
* `awsidr setup-apm` must be completed first
* Custom EventBus must be deployed and accessible
* APM tool must be configured to send alerts to AWS

## APM Setup Command Steps

The `awsidr setup-apm` command consists of 9 steps:

### Step 1: Select Deployment Region

Select the AWS region where the APM integration infrastructure will be deployed. This is where your APM tool will send events.

```
Step 1/9: Select Deployment Region

🌍 APM Integration Infra Deployment Region
→ Enter region for APM deployment (us-east-1): us-east-1

✅ Selected region: us-east-1
```

### Step 2: Select APM Provider

Choose your APM provider from the supported list:

```
Step 2/9: Select APM Provider

Select your APM provider:
  1. Datadog
  2. New Relic
  3. Grafana Cloud
  4. Splunk Observability Cloud
  5. Dynatrace
→ Enter your choice (1-5): 2

✅ Selected: New Relic
```

### Step 3: Review and Update APM Setup Configuration

Review your configuration before proceeding. You can go back and modify if needed.

```
Step 3/9: Review APM Setup Configuration
╭───────────────────────────────────────────────────────────────────────────────────────────────────────── 📋  APM Configuration Review ──────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ Deployment Region: us-east-1                                                                                                                                                                                                                    │
│ APM Provider: New Relic                                                                                                                                                                                                                         │
│ Integration Type: EventBridge Integration (SAAS)                                                                                                                                                                                                │
╰─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
→ Would you like to proceed with this APM configuration? [y/n] (y): y

✅  APM configuration confirmed for integration
```

If you select `n`, the CLI will return to options to modify step 1 or 2 for reconfiguration.

### Step 4: Check Existing Stack

The CLI automatically checks if there is an existing CloudFormation stack related to APM integration for the selected provider:

```
Step 4/9: Check Existing Stack

🔍 Checking for existing New Relic CloudFormation stack...

ℹ️  No existing New Relic stack found. Proceeding with new deployment.
```

If an existing stack is found:

```
✅ Found existing New Relic stack: NewRelic-IntegrationForIDR

ℹ️  Skipping to Step 8 for validation and 9 alarm ingestion.
```

The CLI will skip to Step 8 to validate the existing APM integration setup and proceed to APM alarm ingestion in Step 9.

### Step 5: Integration Prerequisites

Depending on your selected APM provider and integration type, the CLI requires specific prerequisites:

**For EventBridge (SaaS) Partners:**

```
Step 5/9: Integration Prerequisites

→ Do you have a Partner Event Source setup in Amazon EventBridge for New Relic? 
  (example: aws.partner/newrelic.com/123456789012/source_name) [y/n] (y): y
→ Enter partner event source name for New Relic: aws.partner/newrelic.com/1234567/cloudwatch

✅ Validation successful
```

**For SNS Integration Partners:**

```
Step 5/9: Integration Prerequisites

→ Do you have an SNS topic for Grafana Cloud integration? [y/n] (y): y
→ Enter SNS topic ARN: arn:aws:sns:us-east-1:123456789012:grafana-alerts

✅ Validation successful
```

**For Webhook Integration:**

No prerequisites are required. The CloudFormation stack will create all necessary resources for webhook integration including API Gateway, Lambda functions, Secrets Manager, and EventBridge custom event bus.

### Step 6: Configure Incident Detection Event Path

Each APM tool sends alerts in a different JSON payload structure. The CLI uses a default event path to extract the incident name from your APM's payload.

**Important:** You cannot modify this setting after deployment. If you need to change the event path later, you must delete and redeploy the CloudFormation stack.

```
Step 6/9: Configure Incident Detection Event Path
→ Do you have any custom incident detection event path for New Relic? 
(New Relic by default uses: event["detail"]["workflowName"]) [y/n] (n): n

✅ Using default path: event["detail"]["workflowName"]
```

**Custom Event Path:**

If your APM uses a custom payload structure, select `y` and provide the correct path:

```
→ Do you have any custom incident detection event path for New Relic? [y/n] (n): y
→ Enter custom event path: event["detail"]["custom"]["alertName"]

✅ Using custom path: event["detail"]["custom"]["alertName"]
```

### Step 7: Deploy CloudFormation Stack

The CLI deploys a CloudFormation stack that creates the necessary infrastructure for integrating your selected APM with your AWS account. This stack will be created in the region you selected and in the account where you're operating the CLI.

```
Step 7/9: Deploy CloudFormation Stack

📋 CloudFormation Deployment Summary

  • Stack Name: NewRelic-IntegrationForIDR
  • Region: us-east-1
  • Provider: New Relic

→ ⚠️  This will create AWS resources. Proceed with deployment? [y/n] (y): y

📋 CloudFormation Parameters for NewRelic:

  • APMNameParameter: NewRelic
  • PartnerEventBusNameParameter: aws.partner/newrelic.com/1234567/c
  • PartnerEventBusPrefixParameter: aws.partner/newrelic.com
  • Incident Path: event["detail"]["workflowName"]

🚀 Deploying CloudFormation stack: NewRelic-IntegrationForIDR

⏳  NewRelic-IntegrationForIDR stack deployment in progress...

✅ Stack deployment completed successfully!
```

### Step 8: Validate APM Integration

The CLI validates that your APM integration is working correctly by checking if events from your APM provider are reaching the Lambda function. You can test immediately by sending a test alert from your APM, or skip and validate manually later.

**Optional:** The CLI offers an extended wait period (up to 15 minutes) if initial validation doesn't detect events, giving the integration time to initialize and receive test alerts.

```
Step 8/9: Test Integration Readiness

🧪 Testing Your APM Integration

🔍 Optional: Check if webhook events are reaching Lambda
→ Would you like to test the integration now? (You can also test later using the instructions below) [y/n] (y): 

⏳ Waiting for Lambda activity (up to 90 seconds)...

⏱️  Waiting for activity...
⏱️  Waiting for activity...
⏱️  Waiting for activity...

⚠️  ℹ️  No events detected yet - this is normal for new setups

💡 Send a test alert from your APM to verify the integration

⏰ Extended Wait Option:
   • We can wait up to 15 minutes, checking every minute
   • During this time, send a test alert from your APM
   • You can stop waiting at any time by pressing Ctrl+C

→ Would you like to wait up to 15 minutes for Lambda to receive events? [y/n] (y): 

⏳ Starting extended wait (up to 15 minutes)...

💡 Send a test alert from your APM to verify the integration

⏳ Waiting for Lambda activity (up to 900 seconds)...

⏱️  Waiting for activity...
⏱️  Waiting for activity...

✅ Integration test successful - events are being processed!

This validates that your webhook configuration is working.
```

**Important note:** For Dynatrace, webhook configuration is required for sending alerts from APM to AWS account. Follow the [detailed Dynatrace webhook documentation](https://docs.dynatrace.com/docs/analyze-explore-automate/notifications-and-alerting/problem-notifications/webhook-integration).

### Step 9: Ingest APM Alarms to IDR

The CLI provides next steps to ingest the APM alarms/alerts into IDR using the `ingest-alarms` command.

```
Step 9/9: Next Steps

✅ APM integration setup complete!

📋 Next Steps:
1. Configure your APM tool to send alerts to AWS (if not already done)
2. Run alarm ingestion to onboard APM alarms into IDR:

   awsidr ingest-alarms

3. Provide the following information during alarm ingestion:
   • Custom EventBus ARN: [displayed from stack outputs]
   • Alarm identifiers from your APM tool

📖 For detailed alarm ingestion steps, see the Alarm Ingestion section.
```

## APM-Specific Documentation

* **Datadog:** [Amazon EventBridge Integration](https://docs.datadoghq.com/integrations/amazon-event-bridge/)
* **New Relic:** [Auto-remediation using New Relic and Amazon EventBridge](https://newrelic.com/blog/how-to-relic/implement-auto-remediation-using-new-relic-and-amazon-eventbridge)
* **Splunk:** [Send alerts to Amazon EventBridge](https://help.splunk.com/en/splunk-observability-cloud/manage-data/available-data-sources/supported-integrations-in-splunk-observability-cloud/notification-services/send-alerts-to-amazon-eventbridge)
* **Grafana Cloud:** [Configure Amazon SNS](https://grafana.com/docs/grafana/latest/alerting/configure-notifications/manage-contact-points/integrations/configure-amazon-sns/)
* **Dynatrace:** [Webhook Integration](https://docs.dynatrace.com/docs/analyze-explore-automate/notifications-and-alerting/problem-notifications/webhook-integration)

## See Also

- [Main README](../../README.md)
- [Alarm Ingestion](alarm-ingestion.md)
- [CloudWatch Alarms](cloudwatch-alarms.md)
- [Workflows](../workflows.md)
- [IAM Policies](../iam-policies.md)
- [Unattended Mode](../unattended-mode.md)
- [FAQ](../faq.md)
- [Appendix](../appendix.md)
