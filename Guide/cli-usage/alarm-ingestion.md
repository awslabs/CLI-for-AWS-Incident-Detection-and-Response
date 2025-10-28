# Alarm Ingestion

The alarm ingestion workflow consists of 11 steps:

## Step 1: Collect Workload Metadata

The CLI collects basic workload information:

* **Workload name:** A descriptive name for your workload (e.g., PaymentsService-Prod)
* **Regions:** AWS regions where your alarms are deployed (e.g., us-east-1, us-west-2)

```
Step 1/12: Collect Workload Metadata

💡 You can review and update this information in the next step

💡 Enter a descriptive name for this workload (e.g. PaymentsService-Prod, DataPipeline-Dev)
→ Workload name (): MyProductionWorkload

📍 Enter AWS regions where your alarms are deployed (comma-separated)
→ Regions (us-east-1): us-east-1,us-west-2

✅ Workload information collected
```

## Step 2: Review and Update Workload Information

Review the collected workload information and make changes if needed:

```
╭────────────────────────────────── Workload Information Summary ──────────────────────────────────╮
│ Name: MyProductionWorkload                                                                       │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯

→ Would you like to modify any information? [y/n] (n):
```

## Step 3: Collect Alarm Contact Information

Provide contact details for your incident response team:

```
Step 3/12: Collect Alarm Contact Information

📞 Collecting contact details of your company's internal major incident / IT crisis management team.

📞 Primary Incident Contact Information
──────────────────────────────────────

Primary incident contact serves as the initial point of contact for AWS IDR incident and alarm notifications.
→ Primary contact name (): John Doe
→ Primary contact email (): john.doe@company.com
→ Primary contact phone (optional) (): +1-555-123-4567

📞 Escalation Incident Contact Information
─────────────────────────────────────────

Escalation contact will be contacted if primary contact is unreachable during an incident.
→ Would you like to use John Doe as your escalation contact as well? [y/n] (n): n
→ Escalation contact name (): Jane Smith
→ Escalation contact email (): jane.smith@company.com
→ Escalation contact phone (optional) (): +1-555-987-6543
```

## Step 4: Review and Update Contact Information

Review and confirm the alarm contact information:

```
╭────────────────────────────────── Alarm Contact Information Summary ────────────────────────────────╮
│ Primary Name: John Doe                                                                              │
│ Primary Email: john.doe@company.com                                                                 │
│ Primary Phone: +1-555-123-4567                                                                      │
│ Escalation Name: Jane Smith                                                                         │
│ Escalation Email: jane.smith@company.com                                                            │
│ Escalation Phone: +1-555-987-6543                                                                   │
╰─────────────────────────────────────────────────────────────────────────────────────────────────────╯

→ Would you like to modify any alarm contact information? [y/n] (n):
```

## Step 5: Select Alarm Type

Choose what type of alarms would you like to ingest?

```
Step 5/12: Select Alarm Type

🔍 Alarm Ingestion

What would you like to ingest?

Select alarm type:
  1. CloudWatch Alarms
  2. APM Alarms (eg. Datadog, New Relic etc.)
→ Enter your choice (1-2) :
```

## Step 6: Configure Alarm Ingestion

### In case of Cloudwatch Alarms

Choose how you want to provide alarm ARNs:

```
Step 6/12: Configure Alarm Ingestion

🔍 CloudWatch Alarm Ingestion

How would you like to provide alarm ARNs?

Select input method:
  1. Find alarms by tags
  2. Upload a text file with ARNs
  3. Enter ARNs manually
→ Enter number (1-3):
```

**Option 1: Find alarms by tags**

* Discover alarms using AWS resource tags
* Supports single tag (key and value separately) or multiple tags
* Example: Owner=CLI or Environment=Production,Team=Backend

**Option 2: Upload a text file with ARNs**

* Provide a file path containing alarm ARNs (one per line)
* Example file format:

```
arn:aws:cloudwatch:us-east-1:123456789012:alarm:MyAlarm1
arn:aws:cloudwatch:us-east-1:123456789012:alarm:MyAlarm2
```

💡 Generate from AWS CLI:

```
aws cloudwatch describe-alarms --query 'MetricAlarms[].AlarmArn' --output text | tr '\t' '\n' > alarms.txt
```

**Option 3: Enter ARNs manually**

* Enter alarm ARNs directly in the CLI
* Paste multiple ARNs (one per line)
* Press Enter twice when done

### In case of APM Alarms

Enter the region where the CustomEventBus is deployed, as part of the APM Cloudformation stack. The CLI will auto-discover Event Buses deployed in that region with name containing AWSIncidentDetectionResponse

```
Step 6/12: Configure Alarm Ingestion

📡 APM EventBridge Configuration

To ingest APM alarms, we need the EventBridge CustomEventBus that was created as part of your APM CloudFormation stack.

📍 Enter the region where your CustomEventBus is deployed
→ Region: us-east-1

💡 Found eligible EventBridge event buses:

  • arn:aws:events:us-east-1:123456789012:event-bus/NewRelic-AWSIncidentDetectionResponse-EventBus (created: 2025-11-11)
→ Use this event bus: arn:aws:events:us-east-1:123456789012:event-bus/NewRelic-AWSIncidentDetectionResponse-EventBus? [y/n] (y): 

✅ Event bus configured successfully
```

To manually enter an Event Bus ARN, enter 'n' (no) when prompted Use this event bus:

## Step 7: Collect Alarms

### In case of Cloudwatch Alarms

Based on your selected input method, the CLI discovers alarms:

**For tag-based discovery (Option 1):**

```
Step 7/12: Collect Alarms

📍 Select regions to search for alarms
→ Regions (comma-separated): us-west-2,us-east-1

How would you like to specify tags?:
  1. Single tag (key and value separately)
  2. Multiple tags (key1=value1,key2=value1|value2)
→ Enter number (1): 1
→ Tag key (Application): Owner
→ Tag value: CLI
→ Would you like to proceed with Owner=['CLI']? [y/n] (y):

🔍 Searching for CloudWatch alarms...

Searching for CloudWatch alarms in region: us-east-1
✅ Found 4 CloudWatch alarms in region: us-east-1

Searching for CloudWatch alarms in region: us-west-2
✅ Found 4 CloudWatch alarms in region: us-west-2

✅ Found 8 alarm(s) matching tag criteria
```

**For file input (Option 2):**

```
Step 7/12: Collect Alarms

📁 Create a text file with one alarm ARN per line:
  arn:aws:cloudwatch:us-east-1:123456789012:alarm:MyAlarm1
  arn:aws:cloudwatch:us-east-1:123456789012:alarm:MyAlarm2

💡 Generate from AWS CLI:
  aws cloudwatch describe-alarms --query 'MetricAlarms[].AlarmArn' --output text | tr '\t' '\n' > alarms.txt

→ Enter file path containing alarm ARNs (or 'back' to go back): /path/to/alarms.txt

✅ Loaded 8 alarm ARN(s)
```

**For manual input (Option 3):**

```
Step 7/12: Collect Alarms

→ Enter alarm ARNs (comma-separated): arn:aws:cloudwatch:us-east-1:123456789012:alarm:MyAlarm1,arn:aws:cloudwatch:us-east-1:123456789012:alarm:MyAlarm2

✅ Loaded 2 alarm ARN(s)
📍 Detected regions: us-east-1
```

### In case of APM Alarms

Enter the APM alert identifiers manually (comma separated):

```
Step 7/12: Collect Alarms

🏷️  APM Alert Identifiers

Provide comma-separated alert identifiers that your APM sends (e.g., 'error-counts,cpu-utilization,latency').
→ Enter alert identifiers (comma-separated): test1,test2,test3

✅ Configured 3 alert identifier(s)
```

## Step 8: Confirm Configuration

### In case of Cloudwatch Alarms

Review and select which alarms to ingest:

```
Step 8/12: Confirm Configuration

8 alarm(s) found:

us-east-1
   1  TestAlarm-USEast1-4
   2  TestAlarm-USEast1-1
   3  TestAlarm-USEast1-2
   4  TestAlarm-USEast1-3

us-west-2
   5  TestAlarm-USWest2-3
   6  TestAlarm-USWest2-2
   7  TestAlarm-USWest2-1
   8  TestAlarm-USWest2-4

Select alarms:
  • all - select all alarms
  • Numbers/ranges: 1,3 or 1-3 or 1,3-5
  • Region name to select all in that region (e.g., us-west-2)
  • back - return to previous step
→ Selection (all):
```

**Selection options:**

* All alarms: all (select all discovered alarms)
* Specific numbers: 1,3,5 (select alarms 1, 3, and 5)
* Ranges: 1-4 (select alarms 1 through 4)
* Combined: 1,3-5 (select alarm 1 and alarms 3 through 5)
* By region: us-west-2 (select all alarms in us-west-2)
* Go back: back (return to input method selection)

### In case of APM Alarms

Review and confirm the CustomEventBus and APM identifiers provided:

```
Step 8/12: Confirm Configuration

📋 APM Configuration Summary

Event Bus: arn:aws:events:us-east-1:xxxxxxxxxxxx:event-bus/NewRelic-AWSIncidentDetectionResponse-EventBus

Alert Identifiers: test1, test2, test3
→ Proceed with this configuration? [y/n] (y): y
```

If you select 'n' (no):

* The CLI returns to Step 6 (Configure Alarm Ingestion)
* Your APM details are cleared
* You can start with a different Event Bus and identifiers.

## Step 9: Validate Alarms

### In case of Cloudwatch Alarms

The CLI validates selected alarms for noise patterns and suitability:

```
Step 9/12: Validate Alarms

ℹ️  Next, we'll validate these alarms for noise patterns and suitability. Validation results will be noted in your ingestion request.
→ Proceed to validation? [y/n] (y):

🔍 Validating 8 alarm(s)...

Processing TestAlarm-USWest2-3
Processing TestAlarm-USWest2-2
Processing TestAlarm-USWest2-1
Processing TestAlarm-USWest2-4
Processing TestAlarm-USEast1-4
Processing TestAlarm-USEast1-1
Processing TestAlarm-USEast1-2
Processing TestAlarm-USEast1-3

✅ Validation complete
```

**What validation checks:**

* Alarm noise patterns
* Alarm configuration suitability for IDR monitoring
* Historical alarm behavior
* Alarm state transitions

Validation results are included in your support case for IDR team review.

### In case of APM Alarms

APM identifier validation is skipped as it is currently not supported:

```
Step 9/12: Validate Alarms

⏭️  Skipping identifier validation for APM alerts
```

## Step 10: Confirm Ingestion

Review the final summary and confirm ingestion:

```
Step 10/12: Confirm Ingestion

📋 Ready to ingest 8 CloudWatch alarm(s) into IDR

╭────────────────────────────────── Alarm Contact Information Summary ────────────────────────────────╮
│ Primary Name: John Doe                                                                              │
│ Primary Email: john.doe@company.com                                                                 │
│ Primary Phone: +1-555-123-4567                                                                      │
│ Escalation Name: Jane Smith                                                                         │
│ Escalation Email: jane.smith@company.com                                                            │
│ Escalation Phone: +1-555-987-6543                                                                   │
╰─────────────────────────────────────────────────────────────────────────────────────────────────────╯

→ Proceed with ingesting these 8 alarm(s) into IDR? [y/n] (y):

Associating above contact information with 8 alarms

✅ Alarms successfully submitted for IDR onboarding!
```

If you select 'n' (no):

* The CLI returns to Step 5 (Select Alarm Type)
* Your alarm data is cleared
* You can start fresh with a different input method

## Step 11: Working on the Support Case

The CLI creates or updates a support case with your alarm information:

```
Step 11/12: Working on the Support Case

✅ Support case has been created

📋 Support Case ID: case-xxxxxxxxxxxx-muen-xxxx-xxxxxxxxxxxxxxxx

🔗 View case: https://support.console.aws.amazon.com/support/home#/case/?displayId=case-123456789012-muen-2025-d4f7a7485643a48c
```

**Support case behavior:**

* New workload: Creates a new support case
* Existing workload: Updates the existing support case with alarm information
* The support case includes:
  * Workload metadata
  * Alarm ARNs and APM details
  * Contact information
  * Validation results

## Step 12: Check Service Linked Role

The CLI verifies the required Service Linked Role exists:

```
Step 12/12: Check Service Linked Role

Performing sanity check for Service Linked Role (IDR requirement)...

More details about this requirement can be found at this link:
https://docs.aws.amazon.com/IDR/latest/userguide/idr-gs-access-prov.html

✅ Service Linked Role found for IDR alarm ingestion, no action needed
```

If the role is missing:

```
⚠️  Service Linked Role missing for IDR
→ Would you like to create the Service Linked Role for IDR now? [y/n] (y):

✅ Created Service Linked Role: AWSServiceRoleForHealth_EventProcessor
```

## See Also

- [Main README](../../README.md)
- [CloudWatch Alarms](cloudwatch-alarms.md)
- [APM Integration](apm-integration.md)
- [Workload Registration](workload-registration.md)
- [Workflows](../workflows.md)
- [Unattended Mode](../unattended-mode.md)
- [FAQ](../faq.md)
- [Appendix](../appendix.md)
