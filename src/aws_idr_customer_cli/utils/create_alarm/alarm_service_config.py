"""AWS Service configuration for alarm creation - Optimized version.

This configuration maps AWS services to their template files and ARN parsing rules.
Based on: https://repost.aws/selections/KP6FA7iQgVSVeSNq1jAcjwxg/incident-detection-and-response-idr

To add a new service:
1. Add the service constant to AwsServices enum
2. Add the service to AWS_SERVICE_CONFIG using the enum
3. Create the corresponding YAML template file
4. Add ARN parsing rules if needed
"""

from enum import Enum
from functools import lru_cache
from typing import Any, Dict, List, Optional

# Create reverse lookup for better performance
_SERVICE_LOOKUP: Dict[str, "AwsServices"] = {}


class AwsServices(Enum):
    """AWS service names as enum for type safety and auto-completion."""

    ATHENA = "athena"
    KINESIS = "kinesis"

    EVENTBRIDGE = "eventbridge"
    SNS = "sns"
    SQS = "sqs"
    STEPFUNCTIONS = "stepfunctions"

    ELASTICACHE = "elasticache"

    EC2 = "ec2"
    ECS = "ecs"
    EKS = "eks"
    LAMBDA = "lambda"

    DAX = "dax"
    DYNAMODB = "dynamodb"
    KEYSPACES = "keyspaces"
    RDS = "rds"
    REDSHIFT = "redshift"

    IOT = "iot"

    MEDIALIVE = "medialive"
    MEDIAPACKAGE = "mediapackage"

    ALB = "alb"
    APIGATEWAY = "apigateway"
    CLOUDFRONT = "cloudfront"
    DIRECTCONNECT = "directconnect"
    NETWORKFIREWALL = "networkfirewall"
    NLB = "nlb"
    ROUTE53 = "route53"
    ROUTE53RESOLVER = "route53resolver"
    TRANSITGATEWAY = "transitgateway"
    VPN = "vpn"

    WAF = "waf"

    EFS = "efs"
    FSX = "fsx"
    S3 = "s3"

    def __new__(cls, value: str) -> "AwsServices":
        obj = object.__new__(cls)
        obj._value_ = value
        # Build reverse lookup during enum creation for O(1) access
        _SERVICE_LOOKUP[value.lower()] = obj
        return obj


class ProjectDirectories:
    """Constants for project directory names and configuration keys."""

    # Package and directory names
    PACKAGE_NAME = "aws_idr_customer_cli"
    UTILS_DIR = "utils"
    SERVICES_DIR = "services"
    ALARM_CREATE_DIR = "create_alarm"

    # YAML configuration keys
    ALARM_TEMPLATES_KEY = "templates"


# AWS Service Configuration - Using enum keys directly
AWS_SERVICE_CONFIG: Dict[AwsServices, Dict[str, Any]] = {
    # Analytics Services
    AwsServices.KINESIS: {
        "template_file": "idr_alarm_templates/kinesis.yaml",
        "description": "Amazon Kinesis",
        "arn_patterns": ["stream"],
    },
    # Application Integration Services
    AwsServices.EVENTBRIDGE: {
        "template_file": "idr_alarm_templates/eventbridge.yaml",
        "description": "Amazon EventBridge",
        "arn_patterns": ["event-bus", "rule"],
    },
    AwsServices.SNS: {
        "template_file": "idr_alarm_templates/sns.yaml",
        "description": "Amazon Simple Notification Service",
        "arn_patterns": ["topic"],
    },
    AwsServices.SQS: {
        "template_file": "idr_alarm_templates/sqs.yaml",
        "description": "Amazon Simple Queue Service",
        "arn_patterns": ["queue"],
    },
    AwsServices.STEPFUNCTIONS: {
        "template_file": "idr_alarm_templates/stepfunctions.yaml",
        "description": "AWS Step Functions",
        "arn_patterns": ["stateMachine", "execution"],
    },
    # Caching Services
    AwsServices.ELASTICACHE: {
        "template_file": "idr_alarm_templates/elasticache.yaml",
        "description": "Amazon ElastiCache",
        "arn_patterns": ["cluster", "replicationgroup"],
    },
    # Compute Services
    AwsServices.EC2: {
        "template_file": "idr_alarm_templates/ec2.yaml",
        "description": "Amazon Elastic Compute Cloud",
        "arn_patterns": ["instance", "volume", "security-group"],
    },
    AwsServices.EKS: {
        "template_file": "idr_alarm_templates/eks.yaml",
        "description": "Amazon Elastic Kubernetes Service",
        "arn_patterns": ["cluster"],
    },
    AwsServices.LAMBDA: {
        "template_file": "idr_alarm_templates/lambda.yaml",
        "description": "AWS Lambda",
        "arn_patterns": ["function"],
    },
    # Database Services
    AwsServices.DAX: {
        "template_file": "idr_alarm_templates/dax.yaml",
        "description": "Amazon DynamoDB Accelerator (DAX)",
        "arn_patterns": ["cluster"],
    },
    AwsServices.DYNAMODB: {
        "template_file": "idr_alarm_templates/dynamodb.yaml",
        "description": "Amazon DynamoDB",
        "arn_patterns": ["table", "index"],
    },
    AwsServices.KEYSPACES: {
        "template_file": "idr_alarm_templates/Keyspaces.yaml",
        "description": "Amazon Keyspaces (for Apache Cassandra)",
        "arn_patterns": ["keyspace", "table"],
    },
    AwsServices.RDS: {
        "template_file": "idr_alarm_templates/rds.yaml",
        "description": "Amazon Relational Database Service",
        "arn_patterns": ["db", "cluster", "snapshot"],
    },
    AwsServices.REDSHIFT: {
        "template_file": "idr_alarm_templates/redshift.yaml",
        "description": "Amazon Redshift",
        "arn_patterns": ["cluster"],
    },
    # IoT Services
    AwsServices.IOT: {
        "template_file": "idr_alarm_templates/iot.yaml",
        "description": "AWS IoT Core",
        "arn_patterns": ["thing", "rule"],
    },
    # Media Services
    AwsServices.MEDIALIVE: {
        "template_file": "idr_alarm_templates/medialive.yaml",
        "description": "AWS Elemental MediaLive",
        "arn_patterns": ["channel", "input"],
    },
    AwsServices.MEDIAPACKAGE: {
        "template_file": "idr_alarm_templates/mediapackage.yaml",
        "description": "AWS Elemental MediaPackage",
        "arn_patterns": ["channel", "origin-endpoint"],
    },
    # Networking & Content Delivery Services
    AwsServices.ALB: {
        "template_file": "idr_alarm_templates/alb.yaml",
        "description": "Application Load Balancer",
        "arn_patterns": ["loadbalancer", "targetgroup"],
    },
    AwsServices.APIGATEWAY: {
        "template_file": "idr_alarm_templates/apigateway.yaml",
        "description": "Amazon API Gateway",
        "arn_patterns": ["restapis", "apis"],
    },
    AwsServices.CLOUDFRONT: {
        "template_file": "idr_alarm_templates/cloudfront.yaml",
        "description": "Amazon CloudFront",
        "arn_patterns": ["distribution"],
    },
    AwsServices.DIRECTCONNECT: {
        "template_file": "idr_alarm_templates/directconnect.yaml",
        "description": "AWS Direct Connect",
        "arn_patterns": ["connection", "virtualinterface"],
    },
    AwsServices.ROUTE53: {
        "template_file": "idr_alarm_templates/route53.yaml",
        "description": "Amazon Route 53",
        "arn_patterns": ["healthcheck"],
    },
    AwsServices.ROUTE53RESOLVER: {
        "template_file": "idr_alarm_templates/route53resolver.yaml",
        "description": "Amazon Route 53 Resolver",
        "arn_patterns": ["resolver-endpoint"],
    },
    AwsServices.TRANSITGATEWAY: {
        "template_file": "idr_alarm_templates/transitgateway.yaml",
        "description": "AWS Transit Gateway",
        "arn_patterns": ["transit-gateway", "attachment"],
    },
    # Storage Services
    AwsServices.EFS: {
        "template_file": "idr_alarm_templates/efs.yaml",
        "description": "Amazon Elastic File System",
        "arn_patterns": ["file-system", "access-point"],
    },
    AwsServices.S3: {
        "template_file": "idr_alarm_templates/s3.yaml",
        "description": "Amazon Simple Storage Service",
        "arn_patterns": ["bucket"],
    },
}

# ARN Service Name Mapping - Maps AWS ARN service names to IDR service enum values
ARN_SERVICE_NAME_MAPPING: Dict[str, str] = {
    "cassandra": AwsServices.KEYSPACES.value,
    "elasticfilesystem": AwsServices.EFS.value,
    "elasticloadbalancing": AwsServices.ALB.value,
    "events": AwsServices.EVENTBRIDGE.value,
    "medialive": AwsServices.MEDIALIVE.value,
    "mediapackage": AwsServices.MEDIAPACKAGE.value,
    "states": AwsServices.STEPFUNCTIONS.value,
}

# ARN Resource Identifier Extraction Rules - Using enum keys directly
ARN_EXTRACTION_RULES: Dict[AwsServices, Dict[str, str]] = {
    # Analytics Services
    AwsServices.KINESIS: {
        "stream": "stream_name",
    },
    # Application Integration Services
    AwsServices.EVENTBRIDGE: {
        "event-bus": "event_bus_name",
        "rule": "rule_name",
    },
    AwsServices.SNS: {
        "topic": "topic_name",
    },
    AwsServices.SQS: {
        "queue": "queue_name",
    },
    AwsServices.STEPFUNCTIONS: {
        "stateMachine": "state_machine_name",
        "execution": "execution_name",
    },
    # Caching Services
    AwsServices.ELASTICACHE: {
        "cluster": "cluster_id",
        "replicationgroup": "replication_group_id",
    },
    # Compute Services
    AwsServices.EC2: {
        "instance": "instance_id",
        "volume": "volume_id",
        "security-group": "security_group_id",
    },
    AwsServices.EKS: {
        "cluster": "cluster_name",
    },
    AwsServices.LAMBDA: {
        "function": "function_name",
    },
    # Database Services
    AwsServices.DAX: {
        "cluster": "cluster_name",
    },
    AwsServices.DYNAMODB: {
        "table": "table_name",
        "index": "index_name",
    },
    AwsServices.KEYSPACES: {
        "keyspace": "keyspace_name",
        "table": "table_name",
    },
    AwsServices.RDS: {
        "db": "db_instance_identifier",
        "cluster": "db_cluster_identifier",
        "snapshot": "snapshot_id",
    },
    AwsServices.REDSHIFT: {
        "cluster": "cluster_identifier",
    },
    # IoT Services
    AwsServices.IOT: {
        "thing": "thing_name",
        "rule": "rule_name",
    },
    # Media Services
    AwsServices.MEDIALIVE: {
        "channel": "channel_id",
        "input": "input_id",
    },
    AwsServices.MEDIAPACKAGE: {
        "channel": "channel_id",
        "origin-endpoint": "origin_endpoint_id",
    },
    # Networking & Content Delivery Services
    AwsServices.ALB: {
        "loadbalancer": "load_balancer_name",
        "targetgroup": "target_group_name",
    },
    AwsServices.APIGATEWAY: {
        "api_id": "api_id",
        "stage": "stage_name",
    },
    AwsServices.CLOUDFRONT: {
        "distribution": "distribution_id",
    },
    AwsServices.DIRECTCONNECT: {
        "connection": "connection_id",
        "virtualinterface": "virtual_interface_id",
    },
    AwsServices.ROUTE53: {
        "healthcheck": "health_check_id",
    },
    AwsServices.ROUTE53RESOLVER: {
        "resolver-endpoint": "endpoint_id",
    },
    AwsServices.TRANSITGATEWAY: {
        "transit-gateway": "transit_gateway_id",
        "attachment": "attachment_id",
    },
    # Storage Services
    AwsServices.EFS: {
        "file-system": "file_system_id",
        "access-point": "access_point_id",
    },
    AwsServices.S3: {
        "bucket": "bucket_name",
    },
}


class ServiceConfigManager:
    """Optimized manager for AWS service configuration."""

    @staticmethod
    @lru_cache(maxsize=1)
    def get_supported_services() -> List[str]:
        """Get list of all supported service types as strings (cached)."""
        return sorted([service.value for service in AwsServices])

    @staticmethod
    @lru_cache(maxsize=128)
    def get_service_config(service_type: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific service type (cached)."""
        service_enum = _SERVICE_LOOKUP.get(service_type.lower())
        return AWS_SERVICE_CONFIG.get(service_enum) if service_enum else None

    @staticmethod
    @lru_cache(maxsize=128)
    def get_template_file(service_type: str) -> Optional[str]:
        """Get template file name for a service type (cached)."""
        config = ServiceConfigManager.get_service_config(service_type)
        return config.get("template_file") if config else None

    @staticmethod
    @lru_cache(maxsize=128)
    def get_service_description(service_type: str) -> Optional[str]:
        """Get description for a service type (cached)."""
        config = ServiceConfigManager.get_service_config(service_type)
        return config.get("description") if config else None

    @staticmethod
    def is_service_supported(service_type: str) -> bool:
        """Check if a service type is supported (optimized O(1) lookup)."""
        return service_type.lower() in _SERVICE_LOOKUP

    @staticmethod
    @lru_cache(maxsize=128)
    def get_arn_extraction_rules(service_type: str) -> Dict[str, str]:
        """Get ARN extraction rules for a service type (cached)."""
        service_enum = _SERVICE_LOOKUP.get(service_type.lower())
        return ARN_EXTRACTION_RULES.get(service_enum, {}) if service_enum else {}

    @staticmethod
    def get_service_enum(service_type: str) -> Optional[AwsServices]:
        """Get the enum object for a service type string (optimized O(1) lookup)."""
        return _SERVICE_LOOKUP.get(service_type.lower())

    @staticmethod
    def map_arn_service_name(arn_service_name: str) -> str:
        """Map AWS ARN service name to internal service enum value."""
        return ARN_SERVICE_NAME_MAPPING.get(
            arn_service_name.lower(), arn_service_name.lower()
        )

    @staticmethod
    @lru_cache(maxsize=128)
    def get_arn_patterns(service_type: str) -> List[str]:
        """Get ARN patterns for a service type (cached)."""
        config = ServiceConfigManager.get_service_config(service_type)
        return config.get("arn_patterns", []) if config else []

    @staticmethod
    def clear_cache() -> None:
        """Clear all LRU caches - useful for testing or config changes."""
        ServiceConfigManager.get_supported_services.cache_clear()
        ServiceConfigManager.get_service_config.cache_clear()
        ServiceConfigManager.get_template_file.cache_clear()
        ServiceConfigManager.get_service_description.cache_clear()
        ServiceConfigManager.get_arn_extraction_rules.cache_clear()
        ServiceConfigManager.get_arn_patterns.cache_clear()

    @staticmethod
    def get_cache_info() -> Dict[str, Any]:
        """Get cache information for debugging/monitoring."""
        return {
            "get_supported_services": ServiceConfigManager.get_supported_services.cache_info(),
            "get_service_config": ServiceConfigManager.get_service_config.cache_info(),
            "get_template_file": ServiceConfigManager.get_template_file.cache_info(),
            "get_service_description": ServiceConfigManager.get_service_description.cache_info(),
            "get_arn_extraction_rules": ServiceConfigManager.get_arn_extraction_rules.cache_info(),
            "get_arn_patterns": ServiceConfigManager.get_arn_patterns.cache_info(),
        }
