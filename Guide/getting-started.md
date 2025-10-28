# Getting Started

## Prerequisites

Onboarding to IDR requires that we collect information from you. We encode this information in our internal runbooks so our engineers can best serve you during incident response.

**⚠️ Important**: 
- Ensure you have the required IAM permissions. See [IAM Policies](iam-policies.md) for detailed permission requirements.
- If running locally (not in AWS CloudShell), please configure AWS credentials in your environment before execution.

### Standard Requirements
- Regions (in which your AWS resources are used)
- Tags applied to AWS Resources you want to onboard
- Resource identifiers of the AWS resources you want to onboard
- Primary contact name for your alarm response team
- Primary contact email for your alarm response team
- Primary contact phone number for your alarm response team (Optional)
- Escalation alarm contact name (in case primary contact is unreachable)
- Escalation alarm contact email
- Escalation alarm contact phone number (Optional)
- Alarm details for the workload

### Additional Requirements for APM Integration
- Partner EventBridge or SNS integrations
- Configure APM tool webhooks to send alerts to AWS
- AWS resources deployment permissions

## Installation

```
# Install from PyPI
pip install awsidr

# Install from GitHub
pip install git+https://github.com/awslabs/CLI-for-AWS-Incident-Detection-and-Response.git

# Uninstall
pip uninstall awsidr
```

## Update Existing Installation

Simply run the installation commands again to install the latest version.

## Basic Commands

```
# 1. Register your workload (first time)
awsidr register-workload

# 2. Create CloudWatch alarms
awsidr create-alarms

# 3. Ingest existing alarms
awsidr ingest-alarms

# 4. Set up APM integration
awsidr setup-apm
```

## Common Flags

```
-v, --verbose    Enable verbose output
--debug          Enable debug mode
--help           Show help message
-r, --resume     Resume interrupted session (see [Appendix - Progress Saving](appendix.md#progress-saving))
--config         Use config file (unattended mode)
```

## Next Steps

- Review [IAM Policies](iam-policies.md) for required permissions
- Understand the [Workflows](workflows.md)
- Learn about [Unattended Mode](unattended-mode.md) for automation

## See Also

- [Main README](../README.md)
- [Workflows](workflows.md)
- [Workload Registration](cli-usage/workload-registration.md)
- [CloudWatch Alarms](cli-usage/cloudwatch-alarms.md)
- [Alarm Ingestion](cli-usage/alarm-ingestion.md)
- [APM Integration](cli-usage/apm-integration.md)
- [IAM Policies](iam-policies.md)
- [Unattended Mode](unattended-mode.md)
- [FAQ](faq.md)
- [Appendix](appendix.md)
