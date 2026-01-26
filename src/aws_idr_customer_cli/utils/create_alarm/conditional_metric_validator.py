"""Validates CONDITIONAL metrics using service-specific accessors."""

from enum import Enum
from typing import Any, Dict, List

from arnparse import arnparse
from injector import inject

from aws_idr_customer_cli.data_accessors.alarm_accessor import AlarmAccessor
from aws_idr_customer_cli.data_accessors.dynamodb_accessor import DynamoDbAccessor
from aws_idr_customer_cli.data_accessors.keyspaces_accessor import KeyspacesAccessor
from aws_idr_customer_cli.data_accessors.lambda_accessor import LambdaAccessor
from aws_idr_customer_cli.data_accessors.rds_accessor import RdsAccessor
from aws_idr_customer_cli.data_accessors.s3_accessor import S3Accessor
from aws_idr_customer_cli.data_accessors.sns_accessor import SnsAccessor


class AwsService(str, Enum):
    """AWS service identifiers."""

    SNS = "sns"
    LAMBDA = "lambda"
    DYNAMODB = "dynamodb"
    CASSANDRA = "cassandra"  # Keyspaces
    RDS = "rds"
    S3 = "s3"


class MetricName(str, Enum):
    """CONDITIONAL metric names."""

    # SNS
    REDRIVEN_TO_DLQ = "RedrivenToDlq"
    FILTERED_OUT = "FilteredOut"

    # Lambda
    DEAD_LETTER_ERRORS = "DeadLetterErrors"

    # DynamoDB & Keyspaces
    REPLICATION_LATENCY = "ReplicationLatency"

    # RDS
    REPLICA_LAG = "ReplicaLag"

    # S3
    TOTAL_REQUEST_LATENCY = "TotalRequestLatency"


class ConditionalMetricValidator:
    """Validates CONDITIONAL metrics using service-specific accessors."""

    @inject
    def __init__(
        self,
        alarm_accessor: AlarmAccessor,
        sns_accessor: SnsAccessor,
        lambda_accessor: LambdaAccessor,
        dynamodb_accessor: DynamoDbAccessor,
        rds_accessor: RdsAccessor,
        s3_accessor: S3Accessor,
        keyspaces_accessor: KeyspacesAccessor,
    ) -> None:
        self.alarm_accessor = alarm_accessor
        self.sns_accessor = sns_accessor
        self.lambda_accessor = lambda_accessor
        self.dynamodb_accessor = dynamodb_accessor
        self.rds_accessor = rds_accessor
        self.s3_accessor = s3_accessor
        self.keyspaces_accessor = keyspaces_accessor

    def validate_metric_exists(
        self, metric_name: str, resource_arn: str, region: str
    ) -> bool:
        """Validate if CONDITIONAL metric exists using service-specific accessors."""
        try:
            parsed_arn = arnparse(resource_arn)
            service = parsed_arn.service.lower()

            if service == AwsService.SNS:
                return self._validate_sns_metric(metric_name, resource_arn, region)
            elif service == AwsService.LAMBDA:
                return self._validate_lambda_metric(metric_name, resource_arn, region)
            elif service == AwsService.DYNAMODB:
                return self._validate_dynamodb_metric(metric_name, resource_arn, region)
            elif service == AwsService.CASSANDRA:
                return self._validate_keyspaces_metric(
                    metric_name, resource_arn, region
                )
            elif service == AwsService.RDS:
                return self._validate_rds_metric(metric_name, resource_arn, region)
            elif service == AwsService.S3:
                return self._validate_s3_metric(metric_name, resource_arn, region)

            self.alarm_accessor.logger.warning(
                f"Unknown service for CONDITIONAL validation: {service}"
            )
            return False

        except (PermissionError, ValueError):
            raise
        except Exception as e:
            self.alarm_accessor.logger.error(
                f"Error validating CONDITIONAL metric {metric_name} for {resource_arn}: {str(e)}"
            )
            return False

    def _validate_sns_metric(
        self, metric_name: str, resource_arn: str, region: str
    ) -> bool:
        """Validate SNS CONDITIONAL metrics using SNS accessor."""
        if MetricName.REDRIVEN_TO_DLQ in metric_name:
            return self._check_sns_subscriptions_for_property(
                resource_arn, region, "RedrivePolicy", metric_name
            )
        elif MetricName.FILTERED_OUT in metric_name:
            return self._check_sns_subscriptions_for_property(
                resource_arn, region, "FilterPolicy", metric_name
            )
        return False

    def _check_sns_subscriptions_for_property(
        self,
        topic_arn: str,
        region: str,
        property_name: str,
        metric_name: str,
    ) -> bool:
        """Check if any subscription has the specified property configured."""
        response = self.sns_accessor.list_subscriptions_by_topic(topic_arn, region)
        subscriptions: List[Dict[str, Any]] = response.get("Subscriptions", [])

        for subscription in subscriptions:
            sub_arn = subscription.get("SubscriptionArn")
            if not sub_arn or sub_arn == "PendingConfirmation":
                continue

            attrs = self.sns_accessor.get_subscription_attributes(sub_arn, region)
            if property_name in attrs:
                return True

        self.alarm_accessor.logger.warning(
            f"Metric '{metric_name}' not available - no {property_name} "
            f"configured on SNS subscriptions for topic: {topic_arn}"
        )
        return False

    def _validate_lambda_metric(
        self, metric_name: str, resource_arn: str, region: str
    ) -> bool:
        """Validate Lambda CONDITIONAL metrics using Lambda accessor.

        Note: For Lambda@Edge functions, the passed 'region' parameter is the metric
        region (e.g., us-west-2 where CloudWatch metrics exist), but the function
        itself only exists in the region from the ARN (always us-east-1 for Lambda@Edge).
        We must use the ARN region to query the function configuration.
        """
        if metric_name == MetricName.DEAD_LETTER_ERRORS:
            parsed_arn = arnparse(resource_arn)
            # Lambda ARN resource: my-function or my-function:version/alias
            function_name = parsed_arn.resource.split(":")[0]

            # IMPORTANT: Use the region from the ARN, not the passed region parameter
            # For Lambda@Edge, the passed region is the metric region (e.g., us-west-2)
            # but the function only exists in the region from the ARN (us-east-1)
            function_region = parsed_arn.region

            config = self.lambda_accessor.get_function_configuration(
                function_name, function_region
            )

            dlq_config = config.get("DeadLetterConfig", {})
            has_dlq = bool(dlq_config.get("TargetArn"))

            if not has_dlq:
                self.alarm_accessor.logger.warning(
                    f"Metric '{metric_name}' not available - DLQ not configured "
                    f"for Lambda function: {function_name}"
                )
            return has_dlq

        return False

    def _validate_dynamodb_metric(
        self, metric_name: str, resource_arn: str, region: str
    ) -> bool:
        """Validate DynamoDB CONDITIONAL metrics using DynamoDB accessor."""
        if metric_name == MetricName.REPLICATION_LATENCY:
            parsed_arn = arnparse(resource_arn)
            table_name = parsed_arn.resource.split("/")[-1]

            table = self.dynamodb_accessor.describe_table(table_name, region)
            is_global = bool(table.get("GlobalTableVersion"))

            if not is_global:
                self.alarm_accessor.logger.warning(
                    f"Metric '{metric_name}' not available - DynamoDB table "
                    f"is not a global table: {table_name}"
                )
            return is_global

        return False

    def _validate_keyspaces_metric(
        self, metric_name: str, resource_arn: str, region: str
    ) -> bool:
        """Validate Keyspaces CONDITIONAL metrics using Keyspaces accessor."""
        if metric_name == MetricName.REPLICATION_LATENCY:
            parsed_arn = arnparse(resource_arn)
            if "/" in parsed_arn.resource:
                keyspace_name = parsed_arn.resource.split("/", 1)[1].rstrip("/")
            else:
                keyspace_name = parsed_arn.resource

            if not keyspace_name or keyspace_name == "keyspace":
                self.alarm_accessor.logger.warning(
                    f"Invalid keyspace name from ARN: {resource_arn}"
                )
                return False

            keyspace = self.keyspaces_accessor.get_keyspace(keyspace_name, region)

            replication_strategy = keyspace.get("replicationStrategy", "")
            replication_regions = keyspace.get("replicationRegions", [])
            is_multi_region = (
                replication_strategy == "MULTI_REGION" and len(replication_regions) > 1
            )

            if not is_multi_region:
                self.alarm_accessor.logger.warning(
                    f"Metric '{metric_name}' not available - Keyspace does not "
                    f"have multi-region replication: {keyspace_name}"
                )
            return is_multi_region

        return False

    def _validate_rds_metric(
        self, metric_name: str, resource_arn: str, region: str
    ) -> bool:
        """Validate RDS CONDITIONAL metrics using RDS accessor."""
        if metric_name == MetricName.REPLICA_LAG:
            parsed_arn = arnparse(resource_arn)
            db_instance_id = parsed_arn.resource.split(":")[-1]

            instances = self.rds_accessor.describe_db_instances(db_instance_id, region)

            if not instances:
                return False

            instance = instances[0]
            is_replica = bool(instance.get("ReadReplicaSourceDBInstanceIdentifier"))

            if not is_replica:
                self.alarm_accessor.logger.warning(
                    f"Metric '{metric_name}' not available - RDS instance "
                    f"is not a read replica: {db_instance_id}"
                )
            return is_replica

        return False

    def _validate_s3_metric(
        self, metric_name: str, resource_arn: str, region: str
    ) -> bool:
        """Validate S3 CONDITIONAL metrics using S3 accessor."""
        if metric_name == MetricName.TOTAL_REQUEST_LATENCY:
            parsed_arn = arnparse(resource_arn)
            bucket_name = parsed_arn.resource

            try:
                metrics = self.s3_accessor.list_bucket_metrics_configurations(
                    bucket_name, region
                )
            except Exception as e:
                self.alarm_accessor.logger.warning(
                    f"Metric '{metric_name}' validation failed for bucket "
                    f"'{bucket_name}' - unable to check metrics configuration. "
                    f"Verify bucket exists in region '{region}': {str(e)}"
                )
                return False

            has_metrics = len(metrics) > 0

            if not has_metrics:
                self.alarm_accessor.logger.warning(
                    f"Metric '{metric_name}' not available - S3 request metrics "
                    f"not enabled for bucket: {bucket_name}"
                )
            return has_metrics

        return False
