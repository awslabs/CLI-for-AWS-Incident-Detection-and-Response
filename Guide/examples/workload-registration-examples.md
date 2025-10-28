# Workload Registration Examples

## Example 1: Tag-Based Workload Registration

```json
{
  "workload": {
    "name": "MyProductionApp",
    "regions": [
      "us-east-1",
      "us-west-2"
    ]
  },

  "discovery": {
    "method": "tags",
    "tags": {
      "Environment": "Production",
      "Owner": "MyTeam"
    }
  },

  "options": {
    "dry_run": false,
    "output_format": "json"
  }
}
```

## Example 2: ARN-Based Workload Registration

```json
{
  "workload": {
    "name": "MySpecificWorkload",
    "regions": [
      "us-east-1",
      "us-west-2"
    ]
  },

  "discovery": {
    "method": "arns",
    "arns": [
      "arn:aws:elasticloadbalancing:us-east-1:23456789012:loadbalancer/app/my-alb/1f4ab07f7a7ba3b4",
      "arn:aws:lambda:us-east-1:23456789012:function:MyFunction",
      "arn:aws:cloudfront::23456789012:distribution/ETDVYZ87W4H85"
    ]
  },

  "options": {
    "dry_run": true,
    "output_format": "text"
  }
}
```
