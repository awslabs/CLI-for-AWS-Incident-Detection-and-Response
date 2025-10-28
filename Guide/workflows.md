# Workflows

Overview of IDR CLI execution steps

The IDR CLI supports four main workflows for onboarding to AWS Incident Detection and Response.

## Workflow 1: Register Your Workload and Create Alarms

In this workflow, you complete everything you need to do in order to onboard your workload to IDR. The CLI interactively walks you through defining a workload, registering it with the IDR service, and defining the alarms you'd like to onboard.

**When to use:** First-time onboarding of a new workload to IDR.

**Command:**
```
awsidr register-workload
```

**Reference Guide:** [Workload Registration](cli-usage/workload-registration.md) | [CloudWatch Alarm Creation](cli-usage/cloudwatch-alarms.md)

**Steps:**

* Workload Information Collection
    * Collect workload name/region
* Tag-based Resource Discovery
    * Collect AWS resource tag information
    * Filter available AWS resources for alarm creation based on tag information
* Resource Selection
    * User selects specific AWS resources from each region and each resource type
    * IDR CLI will generate alarm recommendations base on these resources
* Support Case Creation
    * IDR CLI creates a support case and attaches collected workload information
* Alarm Contact Information Collection
    * Collect name, email, and phone number of your primary & escalation alarm contacts
* CloudWatch Alarm Recommendation Selection
    * based on AWS resource selection, IDR CLI generates alarm recommendations for these resources
    * User view and select alarms related to each resource to be created
* Create CloudWatch Alarms
    * IDR CLI create selected alarms
    * IDR CLI updates existing support case with alarm information
* Service Linked Role Creation
    * IDR CLI checks if the required Service Linked Role exists in the account
    * IDR CLI offers the option to create Service Linked Role if it does not exist

---

## Workflow 2: Alarm Ingestion (for existing alarms)

In this workflow, you define the alarms you want to onboard to IDR if your workload is already registered and if you already have alarms defined. This workflows helps you onboard your existing alarms without requiring you to go through other steps like workload registration or new alarm creation.

**When to use:** Workload is already registered and you have existing alarms.

**Command:**
```
awsidr ingest-alarms
```

**Reference Guide:** [Alarm Ingestion](cli-usage/alarm-ingestion.md)

**Steps:**

* Workload Information Collection
    * Collect workload name/region
* Alarm Contact Information Collection
    * Collect primary & escalation contact details
* Alarm Discovery
    * Discover existing CloudWatch alarms by tags or ARNs
* Alarm Selection
    * Review and select alarms to ingest
* Alarm Validation
    * Validate alarms for noise patterns and suitability
* Support Case Update
    * Create or update support case with alarm information
* Service Linked Role Creation
    * Check and create Service Linked Role if needed

**Discovery Methods:**
- **Tag-based:** `key1=value1,key2=value2`
- **ARN-based:** Provide file with ARNs or enter manually

---

## Workflow 3: Third-Party APM Integration (Infrastructure Setup Deployment)

In this workflow, the CLI helps you to deploy the infrastructure needed to send your APM alarms from an AWS EventBridge custom event bus to IDR. It also helps with integration testing.

**When to use:** Setting up integration with third-party APM tools.

**Command:**
```
awsidr setup-apm
```

**Reference Guide:** [APM Integration](cli-usage/apm-integration.md)

**Steps:**

* APM Integration Infrastructure Deployment
    * Deploy EventBridge custom event bus
    * Deploy Lambda function for alert processing
    * Deploy API Gateway endpoints for webhook based Integrations
    * Configure IAM roles and permissions required for Integration

**Resources Created:**
- Custom EventBus
- Transform Lambda Function
- IAM Execution Role
- Integration-specific resources (EventBridge Rule, SNS Subscription, or API Gateway)

---

## Workflow 4: Third-Party APM Alert/Alarm Ingestion

In this workflow, the CLI helps you onboard your existing APM alarms into IDR without deploying any additional infrastructure.

**When to use:** After APM integration setup is complete.

**Command:**
```
awsidr ingest-alarms
# Select "APM Alarms" when prompted
```

**Reference Guide:** [Alarm Ingestion](cli-usage/alarm-ingestion.md)

**Prerequisites:**
- APM integration infrastructure deployed (Workflow 3)
- Custom EventBus exists
- APM tool configured to send alerts to AWS

**Steps:**

* Workload Information Collection
    * Collect workload name/region
* Alarm Contact Information Collection
    * Collect primary & escalation contact details
* Custom EventBus Validation
    * Validate deployed EventBus from infrastructure setup
* Alert Identifier collection
    * Collect alert identifiers for incident response
* Support Case Update
    * Create or update support case with APM alert information
* Service Linked Role Creation
    * Check and create Service Linked Role if needed

---

## Workflow Selection Guide

| Scenario | Workflow |
|----------|----------|
| First time onboarding | Workflow 1 |
| Have existing CloudWatch alarms | Workflow 2 |
| Need to integrate APM tool | Workflow 3 |
| Have APM alerts to onboard | Workflow 4 |

## See Also

- [Main README](../README.md)
- [Getting Started](getting-started.md)
- [Workload Registration](cli-usage/workload-registration.md)
- [CloudWatch Alarms](cli-usage/cloudwatch-alarms.md)
- [Alarm Ingestion](cli-usage/alarm-ingestion.md)
- [APM Integration](cli-usage/apm-integration.md)
- [Unattended Mode](unattended-mode.md)
- [IAM Policies](iam-policies.md)
- [FAQ](faq.md)
- [Appendix](appendix.md)
