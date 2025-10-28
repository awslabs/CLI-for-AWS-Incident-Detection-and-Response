# Alarm Creation Examples

## Example 1: Tag-Based Alarm Creation

```
{
  "_usage": "awsidr create-alarms --test-mode --config alarm-config-tag.json",

  "workload": {
    "name": "My Application Workload",
    "regions": ["us-east-1"]
  },

  "contacts": {
    "primary": {
      "name": "John Doe",
      "email": "john.doe@company.com",
      "phone": "+1-555-123-4567"
    },
    "escalation": {
      "name": "Jane Smith",
      "email": "jane.smith@company.com",
      "phone": "+1-555-987-6543"
    }
  },

  "discovery": {
    "method": "tags",
    "tags": {
      "Environment": "Production",
      "Team": "Backend"
    }
  },

  "alarm_selection": {
    "resource_types": ["lambda", "dynamodb"]
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

## Example 2: ARN-Based Alarm Creation

```
{
  "_usage": "awsidr create-alarms --test-mode --config alarm-config-arn.json",

  "workload": {
    "name": "Critical Services Workload",
    "regions": ["us-east-1"]
  },

  "contacts": {
    "primary": {
      "name": "Operations Team",
      "email": "ops@company.com"
    },
    "escalation": {
      "name": "Engineering Manager",
      "email": "eng-manager@company.com",
      "phone": "+1-555-999-0000"
    }
  },

  "discovery": {
    "method": "arns",
    "arns": [
      "arn:aws:elasticloadbalancing:us-east-1:23456789012:loadbalancer/app/critical-alb/xyz789",
      "arn:aws:lambda:us-east-1:23456789012:function:CriticalFunction",
      "arn:aws:dynamodb:us-east-1:23456789012:table/CriticalData"
    ]
  },

  "alarm_selection": {
    "resource_types": ["lambda", "alb", "dynamodb"]
  },

  "options": {
    "dry_run": false,
    "create_support_case": true,
    "update_existing_case": true,
    "create_service_linked_role": true,
    "output_format": "text"
  }
}
```
