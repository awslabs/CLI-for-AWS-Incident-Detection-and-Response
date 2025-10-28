# Unattended Mode

The IDR CustomerCLI supports unattended mode for automated execution without user prompts. This mode is ideal for CI/CD pipelines, scripted deployments, and batch processing scenarios where human interaction is not possible or desired.

Non-interactive mode allows you to:

* Execute workload registration and alarm creation using JSON configuration files
* Run validation and testing with dry-run mode
* Generate structured JSON output for integration with other tools

## Command Syntax

### Workload Registration

```
# Non-interactive workload registration
awsidr register-workload --config <path-to-config-file.json>
```

### Alarm Creation

```
# Non-interactive alarm creation
awsidr create-alarms --config <path-to-config-file.json>
```

### Alarm Ingestion

```
# Non-interactive alarm ingestion
awsidr ingest-alarms --config <path-to-config-file.json>
```

### APM Alarm Ingestion

```
# Non-interactive alarm ingestion
awsidr ingest-alarms --config <path-to-config-file.json>
```

## Configuration File Structure

### Workload Registration Schema

Configuration files for workload registration follow this structure:

```json
{
  "workload": {
    "name": "string",
    "regions": ["string"]
  },
  "discovery": {
    "method": "tags" | "arns",
    // For tag-based discovery:
    "tags": {
      "key1": "value1",
      "key2": "value2"
    }
    // OR for ARN-based discovery:
    "arns": [
      "arn:aws:service:region:account:resource"
    ]
  },
  "options": {
    "dry_run": true | false,
    "output_format": "text" | "json"
  }
}
```

### Alarm Creation Schema

Configuration files for alarm creation follow this structure:

```
{
  "workload": {
    "name": "string",
    "regions": ["string"]
  },
  "contacts": {
    "primary": {
      "name": "string",
      "email": "string",
      "phone": "string" // optional
    },
    "escalation": {
      "name": "string",
      "email": "string",
      "phone": "string" // optional
    }
  },
  "discovery": {
    "method": "tags" | "arns",
    // For tag-based discovery:
    "tags": {
      "key1": "value1",
      "key2": "value2"
    }
    // OR for ARN-based discovery:
    "arns": [
      "arn:aws:service:region:account:resource"
    ]
  },
  "alarm_selection": {
    "resource_types": ["lambda", "alb", "dynamodb", "etc"]
  },
  "options": {
    "dry_run": true | false,
    "create_service_linked_role": true | false,
    "create_support_case": true | false,
    "update_existing_case": true | false,
    "output_format": "text" | "json"
  }
}
```

### Alarm Ingestion Schema for CW alarms

```
{
  "workload": {
    "name": "string",
    "regions": ["string"]  // required only for tag-based discovery
  },
  "contacts": {
    "primary": {
      "name": "string",
      "email": "string",
      "phone": "string"  // optional
    },
    "escalation": {
      "name": "string",
      "email": "string",
      "phone": "string"  // optional
    }
  },
  "discovery": {
    "method": "tags" | "arns",
    "tags": {
      "key1": "value1",
      "key2": "value2"
    }
    // OR
    "arns": [
      "arn:aws:cloudwatch:region:account:alarm:name"
    ]
  },
  "options": {
    "dry_run": true | false,
    "create_service_linked_role": true | false,
    "create_support_case": true | false,
    "update_existing_case": true | false,
    "output_format": "text" | "json"
  }
}
```

### Alarm Ingestion Schema for 3rd party APM alarms

```
{
  "workload": {
    "name": "string",
    "regions": ["string"]  
  },
  "contacts": {
    "primary": {
      "name": "string",
      "email": "string",
      "phone": "string"  // optional
    },
    "escalation": {
      "name": "string",
      "email": "string",
      "phone": "string"  // optional
    }
  },
  "third_party_apm": {
    "eventbridge_arn": "arn:aws:events:us-east-1:123456789012:event-bus/NewRelic-AWSIncidentDetectionResponse-EventBus",
    "alert_identifiers": [
      "alert-cpu-high-123",
      "monitor-memory-456",
      "alert-error-rate-789",
      "alert-response-rate-999"
    ]
  },
  "options": {
    "dry_run": true | false,
    "create_service_linked_role": true | false,
    "create_support_case": true | false,
    "update_existing_case": true | false,
    "output_format": "text" | "json"
  }
}
```

## Unattended Mode Configuration Options

### Workload Section

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| name | string | Yes | Unique workload identifier (appears in support cases) |
| regions | array of strings | Yes | AWS regions where resources are located |

### Alarm Creation Contacts Section:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| primary.name | string | Yes | Primary contact name for alarm notifications |
| primary.email | string | Yes | Primary contact email for alarm notifications |
| primary.phone | string | No | Primary contact phone number |
| escalation.name | string | Yes | Escalation contact name |
| escalation.email | string | Yes | Escalation contact email |
| escalation.phone | string | No | Escalation contact phone number |

### Discovery Section

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| method | string | Yes | Resource discovery method: "tags" or "arns" |
| tags | object | Required for tags method | Key-value pairs for tag-based discovery |
| arns | array of strings | Required for arns method | List of specific resource ARNs |

### Alarm Selection Section (Alarm Creation Only)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| resource_types | array of strings | No | Filter alarms by resource type (e.g., ["lambda", "alb", "dynamodb"]) |

### 3rd party APM alarm Ingestion (APM Alarm Ingestion Only)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| eventbridge_arn | Single string | Required for APM alarm/alert ingestion | Custom EventBridge ARN that receives transformed payload from APM integration |
| alert_identifiers | Array of strings for multiple alert IDs | Required Identifiers to monitor | Alert/alarm identifier names from APM that the user wants to monitor and receive incident response |

### Options Section

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| dry_run | boolean | FALSE | Test mode - no actual changes made |
| output_format | string | "text" | Output format: "text" or "json" |
| create_service_linked_role | boolean | TRUE | Create required service linked role if missing |
| create_support_case | boolean | TRUE | Create or update support case |
| update_existing_case | boolean | TRUE | Update existing support case if found |

## Unattended Mode Resource Discovery Methods

The CLI supports two methods for discovering AWS resources:

### Tag-Based Discovery

Discover resources using AWS resource tags:

```
{
  "discovery": {
    "method": "tags",
    "tags": {
      "Owner": "CLI",
      "Environment": "Production"
    }
  }
}
```

**Use when:** You have consistent tagging across your AWS resources and want to discover resources dynamically based on tag criteria.

### ARN-Based Discovery

Specify exact resources using ARNs:

```
{
  "discovery": {
    "method": "arns",
    "arns": [
      "arn:aws:lambda:us-east-1:123456789:function:my-function",
      "arn:aws:elasticloadbalancing:us-east-1:123456789:loadbalancer/app/my-alb/abc123"
    ]
  }
}
```

**Use when:** You know exactly which resources to include and want precise control over the selection.

## Output Formats

### Text Output (Default)

Provides human-readable output with progress indicators and summaries:

```
╭────────────────────────────────── Workload Information Summary ──────────────────────────────────╮
│ Name: Test Application Workload                                                                  │
│ Regions: us-east-1, us-west-2                                                                    │
╰──────────────────────────────────────────────────────────────────────────────────────────────────╯

🔍 Discovering alarms by tags...
✅ Discovered 8 alarm(s)
✅ Validation: 0 valid, 0 invalid, 8 warnings
✅ Support case updated successfully
✅ Alarm ingestion completed successfully

╭─────────────────────────────────── 📋 Alarm ingestion summary ───────────────────────────────────╮
│ Workload name: Test Application Workload                                                         │
│ Alarms ingested: 8                                                                               │
│ Support case ID: case-123456789012-muen-2025-c4c6f43926eb198d                                    │
│ Service linked role created: No                                                                  │
╰───────────────────────────────────────────────────────────────────────────────────────────────────╯
```

### JSON Output

Provides structured output for programmatic processing:

```
{
  "status": "success",
  "data": {
    "schema_version": "1",
    "idr_cli_version": "1.0",
    "account_id": "123456789012",
    "status": "COMPLETED",
    "created_at": "2025-10-16T16:43:00.584838+00:00",
    "last_updated_at": "2025-10-16T16:43:08.862223+00:00",
    "workload_onboard": {
      "support_case_id": "case-123456789012-muen-2025-c4c6f43926eb198d",
      "name": "Test Application Workload",
      "regions": ["us-east-1", "us-west-2"]
    },
    "alarm_contacts": {
      "primary_contact": {
        "name": "John Doe",
        "email": "john.doe@example.com",
        "phone": "+1-555-123-4567"
      },
      "escalation_contact": {
        "name": "Jane Smith",
        "email": "jane.smith@example.com",
        "phone": ""
      }
    },
    "alarm_arns": [
      "arn:aws:cloudwatch:us-east-1:123456789012:alarm:TestAlarm-USEast1-1",
      "arn:aws:cloudwatch:us-east-1:123456789012:alarm:TestAlarm-USEast1-2"
    ],
    "alarm_validation": [
      {
        "alarm_arn": "arn:aws:cloudwatch:us-east-1:123456789012:alarm:TestAlarm-USEast1-1",
        "onboarding_status": "Needs Customer Confirmation - Alarm requires review and confirmation before onboarding",
        "is_noisy": false,
        "remarks_for_customer": [],
        "remarks_for_idr": ["Critical AWS/EC2 metric - acceptable for IDR"]
      }
    ],
    "alarm_ingestion": {
      "onboarding_alarms": [
        {
          "alarm_arn": "arn:aws:cloudwatch:us-east-1:123456789012:alarm:TestAlarm-USEast1-1",
          "primary_contact": {
            "name": "John Doe",
            "email": "john.doe@example.com",
            "phone": "+1-555-123-4567"
          },
          "escalation_contact": {
            "name": "Jane Smith",
            "email": "jane.smith@example.com",
            "phone": ""
          }
        }
      ],
      "contacts_approval_timestamp": "2025-10-16T16:43:05.217011+00:00"
    }
  }
}
```

## Examples

For detailed unattended mode configuration examples, see:

- [Workload Registration Examples](examples/workload-registration-examples.md)
- [Alarm Creation Examples](examples/alarm-creation-examples.md)
- [Alarm Ingestion Examples](examples/alarm-ingestion-examples.md)

## See Also

- [Main README](../README.md)
- [Getting Started](getting-started.md)
- [Workflows](workflows.md)
- [Workload Registration](cli-usage/workload-registration.md)
- [CloudWatch Alarms](cli-usage/cloudwatch-alarms.md)
- [Alarm Ingestion](cli-usage/alarm-ingestion.md)
- [APM Integration](cli-usage/apm-integration.md)
- [IAM Policies](iam-policies.md)
- [FAQ](faq.md)
- [Appendix](appendix.md)