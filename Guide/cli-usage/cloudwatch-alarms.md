# CloudWatch Alarm Creation

Specifying which alarms IDR should monitor is the second phase of onboarding. One way to specify those alarms is for the CLI to help you create them, and then pass those alarms to IDR. If you do not need help creating alarms because you already have existing alarms in CloudWatch or a third party tool, please refer to [alarm-ingestion](alarm-ingestion.md). After completing workload onboarding, you are ready to receive help from IDR when you raise an inbound case. Alarm onboarding means that alarms automatically trigger incident response from IDR. In this phase, we can help you to deploy and onboard these alarms. You can read more about alarm ingestion in IDR user guide: https://docs.aws.amazon.com/IDR/latest/userguide/idr-gs-onboard-workload.html#alarm-ingestion.

At the end of the workload onboarding session, you will be prompted:

```
→ Would you like to continue with alarm creation for this workload? [y/n] (y):
```

If you enter y , you will enter create-alarms workflow directly. If you enter n , the workload session will complete, and you can proceed to alarm creation by executing awsidr create-alarms when you are ready. Or, you can proceed to the <INGEST EXISTING ALARMS WORKFLOW> 
Regardless of your choice in this step, you can resume your session safely with awsidr create-alarms from there.

## Alarm Contact Collection

The CLI will then prompt you for contact information:

* Primary contact name
* Primary contact email
* Primary contact phone number (optional)
* Escalation contact name
* Escalation contact email
* Escalation contact phone number (optional)

The primary incident contact serves as the initial point of contact for incident and alarm notifications for both cloudwatch and 3rd party alarms. The escalation contact will be contacted if the primary contact is unreachable during an incident.

You can review and edit this information before proceeding to next step. 


## ## Select Resource Discovery Method

You will be presented with an overview of your selected resources in the AWS Resource Selection step. Then you will be prompted with the following question:

```
How would you like to get resources for alarm creation?:
  1. Use saved workload resources
  2. Re-discover and update resources using tags
→ Enter number (1): 1
```

Select 1 if you don't want to change your resource selection (default). If you select 2, you will be able to re-select AWS resources again before proceeding (reference section AWS Resource Selection).

## Select Alarms

At this step, you have already selected your AWS resources and the CLI will generate CloudWatch alarm recommendations based on these resources. For a complete list of available alarm templates, see [Appendix - IDR Alarm Recommendations](appendix.md#idr-alarm-recommendations). You can review and select the alarms you would like to create. Alarms are associated to resources. 

NOTE: if you get to alarm creation by running awsidr create-alarms command, then you'll first need to select the AWS resources that you want CLI to recommend alarms for. The resource selection experience for creating alarms is the same as [workload-registration](workload-registration.md). 

Once you've selected the AWS resources, the CLI will generate alarm recommendations and will help you to review and customize alarm selection. The experience is similar to resource selection. First, you'll see the 'Total alarm view' prompt that will look like this:

```
Alarm Creation Selection
────────────────────────

────────────────
Total alarm view
────────────────

Discovered 83 eligible alarms in 1 regions.

NOTE: Resources not eligible for monitoring like IAM roles, security
groups, and subnets are excluded.

What would you like to do?:
1 → Select all 83 alarms in 1 regions and proceed to submitting
2 → Review and customize alarm selection
→ Enter number (1):
```

If you want to proceed with recommended alarm creation without reviewing them, you can choose option 1 (Select all). Then the CLI will do the 'Final confirmation' prompt before proceeding with the alarm creation. The 'Final confirmation' prompt will look like this:

```
──────────────────
Final confirmation
──────────────────

Selection summary
────────────────────────────
global: 9 selected of 9
us-east-1: 74 selected of 74
────────────────────────────

TOTAL: 83 selected of 83

What would you like to do?:
1 → Confirm and continue with 83 of 83 selected
2 → Edit selection
→ Enter number (1-2):
```

If you want to review the alarm recommendation, you can choose 'Edit selection' (option 2) in the 'Final confirmation' prompt, or choose option 'Review and customize alarm selection' (option 2) in the 'Total alarm view' prompt. Then the CLI will navigate you through specific alarm detail view, starting with the 'Regional view':

```
Alarm Creation Selection
────────────────────────

─────────────
Regional view
─────────────

You ve chosen to review and customize alarm selection.

What would you like to do?:
  1 → Select all 83 alarms in 1 regions and proceed to submitting
  2 → Deselect all 83 alarms
  3 → Accept current selection (Currently 83 selected of 83) and proceed to onboarding
  4 → Review alarms in all (1) regions and customize selection (Currently 83 selected of 83)
  5 → Review global alarms (Currently 9 selected of 9)
  6 → Review us-east-1 alarms (Currently 74 of 74 selected)
→ Enter number (1-6):
```

If you want to review details of all alarms, select the 'Review alarms in all' regions' (option 4), or you can review alarms per region with options 5 and 6. NOTE: the actual option sequence may differ depending on the number of regions and resource types that you have. Then the CLI will present aggregated alarm stats per resource in the selected region:

```
Alarm Creation Selection
────────────────────────

───────────────────────────────────────────────────────────────
Regional view > Alarm group view in All region
───────────────────────────────────────────────────────────────

To change region, use 'Accept and go back' option

Alarm count per type in All region:
  apigateway: 3, selected 3
  dynamodb:table: 4, selected 4
  ec2:instance: 21, selected 21
  elasticache:cluster: 3, selected 3
  elasticloadbalancing:loadbalancer: 3, selected 3
  lambda:function: 24, selected 24
  cloudfront:distribution: 6, selected 6
  rds:db: 5, selected 5
  s3: 3, selected 3
  dax:cache: 3, selected 3
  sqs: 2, selected 2
  sns: 6, selected 6
Currently selected: 83 of 83 alarms

What would you like to do?:
  1 → Select all 83 alarms and go back to "Regional view"
  2 → Deselect all 83 alarms
  3 → Accept current resource selection (83 of 83 alarms selected) and go back to "Regional view"
  4 → Review individual alarms and customize selection
→ Enter number (1-4):
```

To view the actual alarm configuration, choose 'Review individual alarms and customize selection' (Option 4). 

To accept the alarm selection and proceed with alarm creation, you need to select the alarms, navigate back to the 'Regional view' by choosing 'Accept current selection and go back' option. In the 'Regional view', you need to accept the selection by once again choosing the 'Accept current selection' option. Then you'll see the 'Final confirmation' prompt with the summary of you selection, where you need to choose 'Confirm and continue with selection' option.

### Important Note

The IDR CLI automatically validates metrics before recommending CloudWatch alarms. This ensures that only functional alarms are created—alarms that will actually trigger when issues occur in your environment.

### How It Works

When you select resources for monitoring, the CLI follows this process:

1. Analyzes your selected resources and identifies relevant metrics
2. Validates which metrics actually exist in your CloudWatch account
3. Recommends alarms only for available metrics
4. Creates alarms after you confirm the recommendations

This validation prevents the creation of non-functional alarms that would never trigger because their underlying metrics don't exist.

### Understanding Metric Types

The CLI categorizes metrics into three types to determine which need validation:

**Native Metrics (Always Available)**

These standard AWS metrics exist automatically for all running resources.
Examples:

* Lambda: Invocations, Errors, Duration, Throttles
* EC2: CPUUtilization, NetworkIn, NetworkOut
* RDS: DatabaseConnections, CPUUtilization
* SNS: NumberOfNotificationsFailed, NumberOfMessagesPublished

Alarms for these metrics are recommended immediately upon selection.

**Conditional Metrics (Feature-Dependent)**

These metrics only exist if you've enabled specific AWS features. The CLI validates these before recommending alarms.
Examples:

* SNS: NumberOfMessagesPublishedToDLQ (requires Dead Letter Queue)
* SNS: NumberOfNotificationsFilteredOut (requires message filtering)
* Lambda: DestinationDeliveryFailures (requires destinations configured)
* DynamoDB: ReplicationLatency (requires global tables)

Alarms are only recommended if the feature is configured in your account.

**Non-Native Metrics (Advanced Monitoring)**

These metrics require optional monitoring solutions to be explicitly enabled. The CLI validates these before recommending alarms.

Examples:

* EKS Container Insights: Pod/container-level metrics
* Prometheus Integration: Custom application metrics
* RDS Enhanced Monitoring: OS-level metrics

Alarms are only recommended if the monitoring solution is enabled.

**During Alarm Recommendation** the CLI will show you which alarms it recommends based on available metrics:
Example:

```
✓ Found 8 metrics for Lambda function 'my-function'
✓ Recommending 8 CloudWatch alarms
```

**During Alarm Creation** after you confirm, the CLI creates the alarms. If any metrics don't exist, you'll see:
Example:

```
⚠️ Alarm 'DR-SNS-NumberOfMessagesPublishedToDLQ' skipped:
Metric 'NumberOfMessagesPublishedToDLQ' not found in AWS/SNS namespace
```

This is normal—it means the Dead Letter Queue feature isn't configured for this topic.

**Need a Skipped Alarm?**
If an alarm was skipped but you need it:

* Enable the required feature in your AWS account (e.g., configure a DLQ, enable Container Insights, CW detailed metrics)
* Re-run the CLI to re-scan your resources
* The alarm will now be recommended and created

## Create CloudWatch Alarms

In this step you will be prompted whether to create the alarms selected in Select Alarms

```
→ Are you ready to proceed with creating these 79 alarms? [y/n] (y): 
```

If you answer n, the CLI will go back to the Select Alarms step so you can re-select the alarms to be created. If you answer y, the CLI will create the alarms. The CLI will then display alarm creation progress. Among these alarms, there can be alarms successfully created in the progress, alarms that already exists (created by previous CLI executions, we will not re-create them to avoid duplicate), and alarms that failed in the process of creation.

The CLI will onboard alarms that are successfully created and alarms that already exists. The following prompt will be displayed:

```
→ Are you ready to proceed with onboarding these 79 alarms? [y/n] (y): 
```

If you select `n` the CLI will terminate without creating support case, and you can resume execution by executing awsidr create-alarms again.
If you select `y`, a support case will be created (if workload support case does not exist) or updated (if workload support case exists). The CLI will report back the case id associated to the support case created or updated. And the CLI execution will finish at this step.

## Service Linked Role Creation

IDR onboarding requires a Service Linked Role AWSServiceRoleForHealth_EventProcessor ,  we will check if this Service Linked Role exist in your AWS account. If it does not exist, the CLI offers the option to create it:

```
Performing sanity check for Service Linked Role (IDR requirement)...

More details about this requirement can be found at this link: 

https://docs.aws.amazon.com/IDR/latest/userguide/idr-gs-access-prov.html

⚠️  Service Linked Role missing for IDR
→ Would you like to create the Service Linked Role for IDR now? [y/n] (y):  
```

If you answer `y` to the confirm message, the Service Linked Role will be automatically created: 

```
✅ Created Service Linked Role: AWSServiceRoleForHealth_EventProcessor
```

If you answer `n` ,  you can create it later manually:

```
📝 To create the Service Linked Role manually, run:

   aws iam create-service-linked-role --aws-service-name event-processor.health.amazonaws.com
```

## See Also

- [Main README](../../README.md)
- [Workload Registration](workload-registration.md)
- [Alarm Ingestion](alarm-ingestion.md)
- [Workflows](../workflows.md)
- [IAM Policies](../iam-policies.md)
- [FAQ](../faq.md)
- [Appendix](../appendix.md)


