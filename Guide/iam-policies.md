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
4. CloudFormationAccess
5. EventBridgeAccess
6. SNSAccess
7. IAMFullAccess (For Service Linked Role creation)
8. ResourceGroupsandTagEditorReadOnlyAccess
9. AWSCloudShellFullAccess (needed if you execute from cloudshell)
```

**Additional S3 Permissions:**

You will also need to grant permissions for the CLI to get all S3 bucket locations if you plan on onboarding your S3 resources:

```
s3:GetBucketLocation
```

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
