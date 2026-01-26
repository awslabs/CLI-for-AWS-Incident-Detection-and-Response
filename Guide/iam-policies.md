# IAM Policies for IDR Customer CLI

This section helps you ensure that the right IAM policies are in place so you can use the CLI effectively.

## Overview

The IDR CLI requires specific IAM permissions depending on which commands you plan to execute. You can choose between using AWS managed policies for quick setup or custom policies for least privilege access.

## Option 1: Use Managed Policies

You run the IDR CLI in the CloudShell. We also currently support Linux, Ubuntu, MacOS and Windows if you want to run the CLI in another environment. Actions you perform with the CLI require IAM permissions depending on the workflow you use. You can use the following managed AWS IAM policies in general: 

```
1. AmazonEC2ReadOnlyAccess
2. AWSSupportAccess
3. CloudWatchFullAccess
4. AWSCloudFormationFullAccess
5. AmazonEventBridgeFullAccess
6. AmazonSNSFullAccess
7. AWSLambda_FullAccess
8. IAMFullAccess (For Service Linked Role creation)
9. ResourceGroupsandTagEditorReadOnlyAccess
10. AWSCloudShellFullAccess (needed if you execute from cloudshell)
11. AmazonDynamoDBReadOnlyAccess (recommended if onboarding DynamoDB tables)
12. AmazonKeyspacesReadOnlyAccess (recommended if onboarding Keyspaces)
13. AmazonS3ReadOnlyAccess (recommended if onboarding S3 Buckets)
14. AmazonRDSReadOnlyAccess (recommended if onboarding RDS Databases)
```

**Note: Conditional Metric Validation Permissions (11-14)**

For improved alarm creation accuracy, the CLI can validate whether conditional metrics (like DLQ metrics, replica lag, etc.) are available for your resources. Additionally, for Lambda functions, the CLI can detect Lambda@Edge deployments and create region-specific alarms. These permissions are recommended if you plan on onboarding the following resources:

```
lambda:GetFunctionConfiguration    # Validate Lambda DLQ configuration
sns:ListSubscriptionsByTopic       # Validate SNS subscription DLQ/filter policies
sns:GetSubscriptionAttributes      # Validate SNS subscription attributes
dynamodb:DescribeTable             # Validate DynamoDB global table status
rds:DescribeDBInstances            # Validate RDS read replica status
s3:GetBucketLocation               # Get all S3 bucket locations
s3:ListBucketMetricsConfigurations # Validate S3 request metrics configuration
keyspaces:GetKeyspace              # Validate Keyspaces multi-region replication
cloudfront:ListDistributions       # Detect Lambda@Edge associations with CloudFront
cloudfront:GetDistribution         # Retrieve Lambda@Edge configuration from distributions
cloudwatch:GetMetricData           # Scan regions for Lambda@Edge metrics
```

Without these permissions, the CLI will:
- Skip conditional alarms for resources if there is no data for corresponding metrics in the last 14 days
- **Lambda@Edge behavior:**
  - Without `cloudfront:ListDistributions` / `cloudfront:GetDistribution`: Treat Lambda@Edge functions as regular Lambda functions (creating alarms only in us-east-1 instead of all regions where the function executes)
  - Without `cloudwatch:GetMetricData`: Skip Lambda@Edge regional alarm creation entirely (cannot determine which regions have metrics)

## Option 2: Custom Policy (Least Privilege)

You can define customized IAM policies for least privileged access. The IDR CLI requires specific IAM permissions depending on which commands you plan to execute.

### Policy 1: General CLI Operations

**Use this policy for:**
- `awsidr register-workload` - Workload registration
- `awsidr create-alarms` - CloudWatch alarm creation
- `awsidr ingest-alarms` - CloudWatch alarm ingestion

[View Policy 1: General CLI Operations](iam-policies/general-cli.json)

### Policy 2: APM Integration - SaaS (EventBridge)

**Use this policy for:**
- `awsidr setup-apm` with **Datadog**
- `awsidr setup-apm` with **New Relic**
- `awsidr setup-apm` with **Splunk Observability Cloud**

**Resources created:**
- Custom EventBus
- EventBridge Rule
- Transform Lambda Function
- IAM Execution Role
- CloudWatch Log Groups

[View Policy 2: APM SaaS Integration](iam-policies/apm-saas.json)

### Policy 3: APM Integration - SNS

**Use this policy for:**
- `awsidr setup-apm` with **Grafana Cloud**

**Resources created:**
- Custom EventBus
- SNS Topic Subscription
- Transform Lambda Function
- IAM Execution Role
- CloudWatch Log Groups

[View Policy 3: APM SNS Integration](iam-policies/apm-sns.json)

### Policy 4: APM Integration - Webhook (Non-SaaS)

**Use this policy for:**
- `awsidr setup-apm` with **Dynatrace**
- `awsidr setup-apm` with any **custom webhook-based APM**

**Resources created:**
- API Gateway REST API with HTTPS endpoint
- Lambda Authorizer Function
- Transform Lambda Function
- Secrets Manager Secret (for auth token)
- Custom EventBus
- IAM Execution Roles
- API Gateway Usage Plan
- CloudWatch Log Groups

[View Policy 4: APM Webhook Integration](iam-policies/apm-webhook.json)

## Policy Selection Guide

| Command | Recommended Policy |
|---------|-------------------|
| `awsidr register-workload` | [Policy 1](iam-policies/general-cli.json) |
| `awsidr create-alarms` | [Policy 1](iam-policies/general-cli.json) |
| `awsidr ingest-alarms` (CloudWatch) | [Policy 1](iam-policies/general-cli.json) |
| `awsidr setup-apm` (Datadog/New Relic/Splunk) | [Policy 2](iam-policies/apm-saas.json) |
| `awsidr setup-apm` (Grafana Cloud) | [Policy 3](iam-policies/apm-sns.json) |
| `awsidr setup-apm` (Dynatrace/Custom Webhook) | [Policy 4](iam-policies/apm-webhook.json) |
| `awsidr ingest-alarms` (APM) | [Policy 1](iam-policies/general-cli.json) (after setup-apm) |

## How to Create an IAM Policy

For detailed instructions, see [How to create an IAM policy](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_create-console.html).

## See Also

- [Main README](../README.md)
- [Getting Started](getting-started.md)
- [Workflows](workflows.md)
- [APM Integration](cli-usage/apm-integration.md)
- [Workload Registration](cli-usage/workload-registration.md)
- [CloudWatch Alarms](cli-usage/cloudwatch-alarms.md)
- [Alarm Ingestion](cli-usage/alarm-ingestion.md)
- [Unattended Mode](unattended-mode.md)
- [FAQ](faq.md)
- [Appendix](appendix.md)
