# Alarm Ingestion Examples

## Example 1: Tag-Based Alarm Ingestion

```json
{
  "_usage": "awsidr ingest-alarms --config alarm-ingestion-config-tag.json",

  "workload": {
    "name": "Test Application Workload",
    "regions": ["us-east-1", "us-west-2"]
  },

  "contacts": {
    "primary": {
      "name": "John Doe",
      "email": "john.doe@example.com",
      "phone": "+1-555-123-4567"
    },
    "escalation": {
      "name": "Jane Smith",
      "email": "jane.smith@example.com"
    }
  },

  "discovery": {
    "method": "tags",
    "tags": {
      "Owner": "CLI"
    }
  },

  "options": {
    "dry_run": false,
    "create_service_linked_role": true,
    "create_support_case": true,
    "update_existing_case": true,
    "output_format": "text"
  }
}
```

## Example 2: ARN-Based Alarm Ingestion

```json
{
  "_usage": "awsidr ingest-alarms --config alarm-ingestion-config-arn.json",

  "workload": {
    "name": "Test Application Workload",
  },

  "contacts": {
    "primary": {
      "name": "John Doe",
      "email": "john.doe@example.com",
      "phone": "+1-555-123-4567"
    },
    "escalation": {
      "name": "Jane Smith",
      "email": "jane.smith@example.com"
    }
  },

  "discovery": {
    "method": "arns",
    "arns": [
      "arn:aws:cloudwatch:us-east-1:123456789012:alarm:TestAlarm-USEast1-1",
      "arn:aws:cloudwatch:us-east-1:123456789012:alarm:TestAlarm-USEast1-2",
      "arn:aws:cloudwatch:us-west-2:123456789012:alarm:TestAlarm-USWest2-1",
      "arn:aws:cloudwatch:us-west-2:123456789012:alarm:TestAlarm-USWest2-2"
    ]
  },

  "options": {
    "dry_run": false,
    "create_service_linked_role": true,
    "create_support_case": true,
    "update_existing_case": true,
    "output_format": "json"
  }
}
```

## Example 3: APM Alarm Ingestion

```json
{
  "_usage": "awsidr ingest-alarms --config apm-alarm-config-sample.json",

  "workload": {
    "name": "APM Monitoring Workload",
    "regions": ["us-east-1"]
  },

  "contacts": {
    "primary": {
      "name": "John Doe",
      "email": "john.doe@example.com",
      "phone": "+1-555-123-4567"
    },
    "escalation": {
      "name": "Jane Smith",
      "email": "jane.smith@example.com"
    }
  },

  "third_party_apm": {
    "eventbridge_arn": "arn:aws:events:us-east-1:23456789012:event-bus/APM-AWSIncidentDetectionResponse-EventBus",
    "alert_identifiers": [
      "newrelic-alert-cpu-high-123",
      "datadog-monitor-memory-456",
      "splunk-alert-error-rate-789",
      "custom-apm-alert-latency-999"
    ]
  },

  "options": {
    "dry_run": false,
    "create_service_linked_role": true,
    "create_support_case": true,
    "update_existing_case": true,
    "output_format": "json"
  }
}
```
