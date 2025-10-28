# FAQ

## General

### How does progress saving and resume work?

The progress is saved when each step completes. For example, if the last CLI execution is interrupted at step 4 in register-workload, then upon re-execution of `awsidr register-workload`, it will prompt you to resume from step 4, using the previous workload. By default, it resumes the last executed session. You can specify a resume session id instead to resume a different session. For more details, see [Appendix - Progress Saving](appendix.md#progress-saving).

### When should I execute register-workload or create-alarms?

If you have not onboarded your workload before, you should execute `awsidr register-workload` first.

At the end of the register-workload session, you will reach the Alarm Creation Handoff step. To continue interrupted sessions from there, you should execute `awsidr create-alarms`. For more details, please check Alarm Creation Handoff section in this document. If you have already onboarded your workload (without CustomerCLI), feel free to execute `awsidr create-alarms` independently.

### What if I want to create alarms for an already onboarded workload?

You can execute `awsidr create-alarms` independently without register-workload. In that case we will only collect workload information necessary for alarm creation. This option is only recommended if you have already completed workload onboarding prior to the release of Customer CLI. If you choose this option, please reference section Workload Information Collection, and Select Resource Discovery Method to select AWS resources for alarm creation. The alarm creation procedure will be the same, you can reference Select Alarms, and Create CloudWatch Alarms.

### Can I resume IDR Customer CLI execution on a different AWS account?

At this stage IDR Customer CLI does not support cross account execution. The progress is saved locally during execution, and previous progress cannot be resumed from a different account.

### What if I have existing alarms and do not need to create new alarms?

In that case you can directly onboard your alarms. We recommend using the `awsidr ingest-alarms` command. You can reference [alarm-ingestion](cli-usage/alarm-ingestion.md)

### What if I have third party Application Performance Monitoring (APM) tools that I would like to ingest?

Integration infrastructure needs to be setup for third party APM. Please reference Ingest Alarms for more detail.

---

### What data gets transmitted in the support case?

When you run awsidr commands, the CLI creates or updates an AWS Support case with a JSON attachment. You can find the content of the attachment [here](support-case-attachment.md)

## Alarm Ingestion

### Can I ingest alarms from multiple regions?

Yes, both interactive and non-interactive modes support multi-region alarm ingestion.

### What happens if I cancel during confirmation?

If you select 'n' during Step 9 (Confirm Ingestion), the CLI returns to Step 5 (Select Input Method) and clears your alarm data. You can start fresh with a different input method.

### Can I update an existing alarm ingestion?

Yes, if you run `awsidr ingest-alarms` for a workload that already has a support case, the CLI will update the existing case with new alarm information.

### How do I know which alarms passed validation?

Validation results are included in the support case created by the CLI. The IDR team will review these results during onboarding.

### Can I use alarm ingestion without prior workload registration?

Yes, `awsidr ingest-alarms` can be run independently. It will collect the necessary workload information during the workflow.

### What's the difference between interactive and non-interactive modes?

* **Interactive mode:** Step-by-step prompts, progress saving, resume capability
* **Non-interactive mode:** Automated execution using configuration file, suitable for CI/CD pipelines

### Which discovery method should I use?

* **Tag-based:** Best when you have consistent tagging across your alarms
* **File input:** Best for bulk operations or when you have a pre-generated list of alarm ARNs
* **Manual input:** Best for small numbers of alarms or one-off ingestions

---

## APM Integration

### Can I set up APM integration for multiple AWS accounts and regions?

No, the `awsidr setup-apm` command deploys infrastructure in a single AWS account and region. You must run the command separately in each account and region where you want to ingest APM alerts.

### What should I do if my APM tool has alerts from multiple AWS accounts and workloads?

IDR recommends deploying the integration infrastructure stack in each AWS account that contains workload resources.

If you require a centralized account setup where a single account receives alerts from multiple workloads across different accounts, please contact AWS IDR and TAM to request guidance for this specialized configuration.

### Can I use alarm ingestion for APM alarms without prior APM setup?

No, APM alarm ingestion requires the custom EventBus created during the `awsidr setup-apm` workflow. You must complete the APM setup (Step 1-9) before you can ingest APM alarms into IDR.

**Workflow order:**
1. Run `awsidr setup-apm` to deploy integration infrastructure
2. Configure your APM tool to send alerts to AWS
3. Use alarm ingestion to onboard APM alarms into IDR

### Do I get onboarding guidance before or after APM integration?

Yes, AWS offers onboarding guidance sessions with AWS engineers to help you with:
* Pre-deployment planning and architecture review
* APM integration setup (`awsidr setup-apm`)

**Requirements:**
* Each APM tool requires its own CloudFormation stack deployment
* Each APM tool gets its own API Gateway endpoint (for webhook integrations) or EventBridge configuration (for SaaS integrations)
* All APM alerts are routed to the same IDR workload using the workload name

### What's the difference between APM alert ingestion and CloudWatch alarm ingestion?

APM alert ingestion processes alerts from third-party tools through custom event bus, while CloudWatch alarm ingestion works directly with AWS CloudWatch alarms. Both can be used together in the same workload.

### Can I use one policy for all CLI commands?

Yes, you can combine Policy 1 with Policy 4 (Webhook) to cover all scenarios, but this grants more permissions than necessary for most use cases.

### I'm using multiple APM tools. Which policy should I use?

Use Policy 4 (Webhook) as it includes all permissions needed for any APM integration type.

### Why are delete permissions included?

Delete permissions are required for CloudFormation stack updates, rollbacks, and cleanup operations. Without them, you cannot modify or remove deployed integrations.

### Can I restrict permissions to specific resources?

Yes, you can add resource-level restrictions using ARN patterns. For example:

```json
"Resource": "arn:aws:lambda:*:*:function:*-AWSIncidentDetectionResponse-*"
```

---

## See Also

- [Main README](../README.md)
- [Getting Started](getting-started.md)
- [Workflows](workflows.md)
- [Workload Registration](cli-usage/workload-registration.md)
- [CloudWatch Alarms](cli-usage/cloudwatch-alarms.md)
- [Alarm Ingestion](cli-usage/alarm-ingestion.md)
- [APM Integration](cli-usage/apm-integration.md)
- [Unattended Mode](unattended-mode.md)
- [IAM Policies](iam-policies.md)
- [Appendix](appendix.md)
