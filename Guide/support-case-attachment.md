# Support Case Attachment

After executing the IDR CLI with the following command:

```
awsidr register-workload
awsidr create-alarms
awsidr ingest-alarms
```

the CLI creates or updates an AWS Support case with a JSON attachment containing the following information:

## Command Metadata

- Command type executed (workload registration, alarm creation, alarm ingestion, or APM setup)
- CLI version and schema version
- AWS account ID
- Session count (increments each time you pause and resume the command)
- Execution mode (interactive or non-interactive)
- Timestamps (command creation, last update, contact approvals, alarm creation, APM configuration)

## Resource Information

- Resource ARNs (e.g., `arn:aws:lambda:us-east-1:123456789012:function:my-function`)
- Resource types, names, and regions
- Resource discovery methods used (tags, manual selection)
- Resource tags applied during discovery

## Workload Details

- Workload name and selected AWS regions

## Alarm Configuration (when applicable)

- CloudWatch alarm ARNs and names
- Alarm creation status
- Associated resource ARNs for each alarm

## Contact Information

- Primary and escalation contact details (name, email, phone)

## APM Integration (when applicable)

- APM provider name (e.g., New Relic, Datadog)
- EventBridge ARNs and alert identifiers
- Deployment region and configuration status
- SNS topic ARNs (if configured)

## Progress Tracking

- Current step and completed steps (in interactive mode only)
- Command execution status (successful or failed)

For more details of the structure of the support case attachment, please reference [data.py](../src/aws_idr_customer_cli/services/file_cache/data.py)

### Data Transmission

- JSON attachments to AWS Support cases
- Automatic splitting into multiple parts when data exceeds 5MB or 300 alarms
- Efficient batching to stay within AWS Support case service limits