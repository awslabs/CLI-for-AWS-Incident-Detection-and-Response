# AWS Incident Detection and Response (IDR) CLI

## Overview

The AWS Incident Detection and Response Customer CLI (referred to as the "IDR CLI" or "CLI" in this package) is a command-line-interface tool that streamlines how you onboard to AWS Incident Detection and Response ("IDR"). You can read more about IDR onboarding in the User Guide: https://docs.aws.amazon.com/IDR/latest/userguide/getting-started-idr.html

The CLI runs in AWS CloudShell or local terminal to collect onboarding information, gather AWS resource data via the Resource Groups Tagging API, and manage Support cases. It creates new CloudWatch alarms or ingests existing ones, and deploys infrastructure via CloudFormation to enable third-party tools to send alerts to AWS for IDR ingestion.

If you’re familiar with the CLI but have questions, [jump to the FAQs](Guide/faq.md) . This section describes what you can accomplish with the CLI. You can use the CLI both in an interactive mode in which the CLI guides you through the steps, or you can [use the CLI in “unattended mode”](Guide/unattended-mode.md) to automate your work. 

## Quick Start

**Prerequisites**: AWS credentials configured (not needed in CloudShell) and required IAM permissions - see [Getting Started](Guide/getting-started.md) and [IAM Policies](Guide/iam-policies.md)

```
# Install IDR CLI
pip install awsidr

# 1. Workload Metadata Collection (Execute this first)
awsidr register-workload

# 2. CloudWatch Alarm Creation (Execute this if your workload information is already collected)
awsidr create-alarms

# 3. Alarm Ingestion (Onboard existing CloudWatch alarms and apm alarms)
awsidr ingest-alarms

# 4. 3rd party APM Integration setup (Set up integration between 3rd party APM providers and AWS account)
awsidr setup-apm

# Available flags
-v, --verbose  Enable verbose output
--debug        Enable debug mode
--help         Show help message and exit.
-r, --resume   Resume with a specific session number
--config       Use config file (unattended mode)
```

### Choosing Which Command to Execute

| Task | Guide |
|------|-------|
| First time setup | [Workflow 1](Guide/workflows.md#workflow-1-register-your-workload-and-create-alarms) |
| Ingest existing alarms | [Workflow 2](Guide/workflows.md#workflow-2-alarm-ingestion-for-existing-alarms) |
| APM integration | [Workflow 3](Guide/workflows.md#workflow-3-third-party-apm-integration-infrastructure-setup-deployment) |
| Automate with config files | [Unattended Mode](Guide/unattended-mode.md) |
| Troubleshooting | [FAQ](Guide/faq.md) |

### Detailed Command Execution Guides

These guides contain the step-by-step walkthrough for each command. You can reference them for explanation of each step during command execution:

- `awsidr register-workload` → [Workload Registration Guide](Guide/cli-usage/workload-registration.md) - Collect workload metadata, discover resources using tags, select AWS resources for monitoring, and create support cases
- `awsidr create-alarms` → [CloudWatch Alarms Guide](Guide/cli-usage/cloudwatch-alarms.md) - Create new CloudWatch alarms with CLI-generated recommendations based on your selected AWS resources
- `awsidr ingest-alarms` → [Alarm Ingestion Guide](Guide/cli-usage/alarm-ingestion.md) - Onboard existing CloudWatch alarms or APM alerts using tags, ARNs, or file uploads; includes validation and support case management
- `awsidr setup-apm` → [APM Integration Guide](Guide/cli-usage/apm-integration.md) - Deploy infrastructure for third-party APM tools (Datadog, New Relic, etc.)

### Examples Input for Unattended Mode

If you chooses to execute in [Unattended Mode](Guide/unattended-mode.md), a configuration file input is needed, you can reference the following examples for configuration file format

- [Workload Registration Examples](Guide/examples/workload-registration-examples.md)
- [Alarm Creation Examples](Guide/examples/alarm-creation-examples.md)
- [Alarm Ingestion Examples](Guide/examples/alarm-ingestion-examples.md)

### AWS IDR Resources

- [AWS Incident Detection and Response](https://aws.amazon.com/premiumsupport/aws-incident-detection-response/)
- [AWS IDR User Guide](https://docs.aws.amazon.com/IDR/latest/userguide/)
- [Getting Started with IDR](https://docs.aws.amazon.com/IDR/latest/userguide/getting-started-idr.html)
- [Onboard Your Workload](https://docs.aws.amazon.com/IDR/latest/userguide/idr-gs-onboard-workload.html)
- [Define and Configure Alarms](https://docs.aws.amazon.com/IDR/latest/userguide/idr-gs-alarms.html)
- [Ingest Alarms](https://docs.aws.amazon.com/IDR/latest/userguide/idr-gs-ingest-alerts.html)
- [Ingest Alarms from APMs with EventBridge Integration](https://docs.aws.amazon.com/IDR/latest/userguide/idr-gs-ingest_alarms_from_apm_to_eventbridge.html)
- [Ingest Alarms Using Webhooks](https://docs.aws.amazon.com/IDR/latest/userguide/idr-ingesting-alarms-using-webhooks.html)
- [Monitoring and Observability](https://docs.aws.amazon.com/IDR/latest/userguide/observe-idr.html)

## Questions, Special Requests, and Feedback

Upon the completion of `awsidr register-workload`, `awsidr create-alarms`, or `awsidr ingest-alarms` , a support case will be created by the CLI on your behalf. If you have any questions about IDR, special requests (such as applicable compliance and regulatory requirements), and feedback for the IDR CLI, please feel free to reply to the support case created. The support case can be found in AWS Support → Your support case, and will have the subject line:

```
AWS Incident Detection and Response - {workload_name}
```

## Contributing

Contributions are welcome! However, changes must go through our internal repository before being merged on GitHub, so external pull requests will not be merged directly.

For security related issues, please reference [SECURITY](SECURITY.md). For non-security related requests, please open issues to report bugs or suggest features. When filing an issue, check existing open or recently closed issues to ensure it hasn't already been reported. Include as much information as possible, such as:

* A reproducible test case or series of steps
* The version of our code being used
* Any modifications you've made relevant to the bug
* Anything unusual about your environment or deployment

## Security

See [SECURITY](SECURITY.md) for more information.

## License

This library is licensed under the Apache-2.0 License. See the [LICENSE.md](LICENSE.md) file.
