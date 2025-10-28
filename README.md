# AWS Incident Detection and Response (IDR) CLI

A command-line interface tool that streamlines onboarding to AWS Incident Detection and Response (IDR). For more information about this IDR onboarding tool, please check the [User Guide](https://docs.aws.amazon.com/IDR/latest/userguide/getting-started-idr.html).

## Overview

The AWS IDR CLI provides a streamlined experience to onboard your AWS workloads to the AWS Incident Detection and Response service. It collects necessary onboarding information, gathers AWS resource information using the AWS Resource Groups Tagging API, deploys AWS CloudWatch alarms, and manages your onboarding Support cases.

## Prerequisites

- AWS Account
- IAM permissions for IDR operations. The following managed policies are recommended:
  1. AmazonEC2ReadOnlyAccess
  2. AWSCloudShellFullAccess
  3. AWSCodeArtifactReadOnlyAccess
  4. AWSSupportAccess
  5. CloudWatchFullAccess
  6. IAMFullAccess (for Service Linked Role creation)
  7. ResourceGroupsandTagEditorReadOnlyAccess
  
  For policies that apply least privileged access, please check the [User Guide](https://amazon.awsapps.com/workdocs-amazon/index.html#/document/4d310922ae42b6205fd7c171590f0f8a1871d5fc6b4cf618efbc1cb79d5c27ef).
- Python 3.x

The AWS IDR CLI collects the following information:
* Regions where your AWS resources are deployed
* Tags applied to the AWS resources you want to onboard (Option 1)
* Resource identifiers of the AWS resources you want to onboard (Option 2)
* Primary contact name for your alarm response team
* Primary contact email for your alarm response team
* Primary contact phone number for your alarm response team (optional)
* Escalation contact name (if primary contact is unreachable)
* Escalation contact email
* Escalation contact phone number (optional)
* Alarm details for the workload

## Installation

```bash
pip install aws-idr-cli
```

## Key Features

- **Workload Onboarding**: Register and onboard workloads for monitoring
- **Alarm Creation**: Create CloudWatch alarms based on selected resources
- **Alarm Ingestion**: Ingest existing alarms for monitoring
- **Unattended Mode**: Automate execution without user prompts, ideal for CI/CD pipelines, scripted deployments, and batch processing scenarios

## Usage

### Workload Onboarding

Onboard workloads to IDR for monitoring and incident detection:

```bash
idrcli register-workload
```

### Alarm Creation

Create CloudWatch alarms based on resources in your workload:

```bash
idrcli create-alarm
```

### Alarm Ingestion

Configure alarm ingestion for your workloads:

```bash
idrcli ingest-alarms
```

### Unattended Mode

Run commands in unattended mode using a configuration file:

```bash
idrcli register-workload --config <path-to-config-file.json>
idrcli create-alarm --config <path-to-config-file.json>
idrcli ingest-alarm --config <path-to-config-file.json>
```
For configuration file syntax, please check the [User Guide](https://amazon.awsapps.com/workdocs-amazon/index.html#/document/4d310922ae42b6205fd7c171590f0f8a1871d5fc6b4cf618efbc1cb79d5c27ef).

## Documentation

- [AWS Incident Detection and Response](https://aws.amazon.com/premiumsupport/aws-incident-detection-response/)
- [IDR Customer CLI User Guide](https://amazon.awsapps.com/workdocs-amazon/index.html#/document/4d310922ae42b6205fd7c171590f0f8a1871d5fc6b4cf618efbc1cb79d5c27ef)
- [AWS IDR User Guide](https://docs.aws.amazon.com/IDR/latest/userguide/)
- [Getting Started with IDR](https://docs.aws.amazon.com/IDR/latest/userguide/getting-started-idr.html)

## Contributing

Contributions are welcome! However, changes must go through our internal repository before being merged on GitHub, so pull requests will not be merged directly.

Please open issues to report bugs or suggest features. When filing an issue, check existing open or recently closed issues to ensure it hasn't already been reported. Include as much information as possible, such as:

* A reproducible test case or series of steps
* The version of our code being used
* Any modifications you've made relevant to the bug
* Anything unusual about your environment or deployment

## Security

See [SECURITY](SECURITY.md) for more information.

## License

This library is licensed under the Apache-2.0 License. See the [LICENSE.md](LICENSE.md) file.
