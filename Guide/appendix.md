# Appendix

## Progress Saving

The CLI will store progress information in a local file cache. The local file cache is a local directory that saves files that record progress and onboarding information during execution of the IDR Customer CLI. You can find this directory at ~/.aws-idr/cache
A typical local cache file name looks like idr-cx-cli_20250805163942882934.enc
These cache files are encrypted and not meant to be edited or accessed directly.
Cache file names are consistent with the session numbers. So in this example, you can resume session from that specific cache by executing with flag --resume idr-cx-cli_20250805163942882934 

## Resources IDR Customer CLI does not onboard

If you find resources count to be less than expected when doing AWS Resource Discovery, it is likely because they are in the category considered as non-functional resources. The CLI will not create alarms for these resources and will not display them to you. For the complete list of functional and non-functional resources, see [functional_resource_config.py](../src/aws_idr_customer_cli/utils/resource_filtering/functional_resource_config.py).

## APM Integrations

### Integration Resources

#### Resources Created by Integration Type

**Common Resources (All Types)**

| Resource | Purpose |
|----------|---------|
| Custom EventBus | Routes normalized events to IDR |
| Transform Lambda | Extracts incident identifier from APM payload |
| IAM Execution Role | Lambda permissions for EventBridge and CloudWatch |

Created by all integration types: 3 core resources

**Type-Specific Resources**

| Integration Type | Additional Resources | Total Resources |
|-----------------|---------------------|-----------------|
| EventBridge (SaaS) | EventBridge Rule | 4 resources |
| SNS | SNS Topic Subscription | 4 resources |
| Webhook | API Gateway (4 components)<br>Secrets Manager<br>Lambda Authorizer<br>Authorizer IAM Role | 10 resources |

#### Resource Naming Pattern

All resources follow: `{APMName}-AWSIncidentDetectionResponse-{ResourceType}`

Example for Dynatrace:
* EventBus: `Dynatrace-AWSIncidentDetectionResponse-EventBus`
* Transform Lambda: `Dynatrace-AWSIncidentDetectionResponse-Lambda-Transform`
* API Gateway: `Dynatrace-AWSIncidentDetectionResponse-APIGW` (webhook only)

## IDR Alarm Recommendations

### ALB

| Business Objectives | AWS Service | Namespace | Metric name | Reactive/Proactive | Metric Classification | Threshold | Recommended alarm configuration | Use case |
|---------------------|-------------|-----------|-------------|--------------------|-----------------------|-----------|---------------------------------|----------|
| RELIABILITY | ALB | AWS/ApplicationELB | HTTPErrorRate | Reactive | Native | > 5.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors ratio of HTTP errors (4XX+5XX) to total requests for application stability |
| RELIABILITY | ALB | AWS/ApplicationELB | RejectedConnectionCount | Proactive | Native | >= 1.0 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors rejected connections when load balancer reaches maximum capacity |
| RELIABILITY | ALB | AWS/ApplicationELB | TargetResponseTime | Reactive | Native | >= 1.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors time elapsed from request leaving load balancer until target starts sending response headers |

### API Gateway

| Business Objectives | AWS Service | Namespace | Metric name | Reactive/Proactive | Metric Classification | Threshold | Recommended alarm configuration | Use case |
|---------------------|-------------|-----------|-------------|--------------------|-----------------------|-----------|---------------------------------|----------|
| RELIABILITY | API Gateway | AWS/API Gateway | (m1/m2)*100<br>m1 = Errors<br>m2 = Invocations | Reactive | Native | >= 5.0 | Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors API error rates as a percentage of total traffic using math expression |
| PERFORMANCE | API Gateway | AWS/ApiGateway | Latency | Reactive | Native | >= 5000.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Response time monitoring provides insight into end user experience and performance |
| PERFORMANCE | API Gateway | AWS/ApiGateway | IntegrationLatency | Reactive | Native | >= 3000.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Measures the time taken between when API Gateway forwards a request to the backend and receives a response |

### CloudFront

| Business Objectives | AWS Service | Namespace | Metric name | Reactive/Proactive | Metric Classification | Threshold | Recommended alarm configuration | Use case |
|---------------------|-------------|-----------|-------------|--------------------|-----------------------|-----------|---------------------------------|----------|
| RELIABILITY | CloudFront | AWS/CloudFront | (m1/m2)*100<br>m1 = Errors<br>m2 = Invocations | Reactive | Native | > 5.0 | Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors the ratio of HTTP 5xx server error responses to total requests |

### DAX

| Business Objectives | AWS Service | Namespace | Metric name | Reactive/Proactive | Metric Classification | Threshold | Recommended alarm configuration | Use case |
|---------------------|-------------|-----------|-------------|--------------------|-----------------------|-----------|---------------------------------|----------|
| RELIABILITY | DAX | AWS/DAX | FaultRequestCount | Reactive | Native | >= 1.0 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors HTTP 500 server errors from DAX |
| RELIABILITY | DAX | AWS/DAX | FailedRequestCount | Reactive | Native | >= 1.0 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors failed requests from DAX |
| RELIABILITY | DAX | AWS/DAX | ThrottledRequestCount | Reactive | Native | >= 1.0 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors throttled requests from DAX |

### Direct Connect

| Business Objectives | AWS Service | Namespace | Metric name | Reactive/Proactive | Metric Classification | Threshold | Recommended alarm configuration | Use case |
|---------------------|-------------|-----------|-------------|--------------------|-----------------------|-----------|---------------------------------|----------|
| RELIABILITY | Direct Connect | AWS/DX | ConnectionState | Reactive | Native | < 0.5 | Statistic = Maximum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = breaching | The state of the connection. 1 indicates up and 0 indicates down |

### DynamoDB

| Business Objectives | AWS Service | Namespace | Metric name | Reactive/Proactive | Metric Classification | Threshold | Recommended alarm configuration | Use case |
|---------------------|-------------|-----------|-------------|--------------------|-----------------------|-----------|---------------------------------|----------|
| RELIABILITY | DynamoDB | AWS/DynamoDB | ReadThrottleEvents | Proactive | Native | >= 5.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors read throttle events to detect capacity issues |
| RELIABILITY | DynamoDB | AWS/DynamoDB | WriteThrottleEvents | Proactive | Native | >= 5.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors write throttle events to detect capacity issues |
| RELIABILITY | DynamoDB | AWS/DynamoDB | SuccessfulRequestLatency | Reactive | Native | >= 100.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors successful request latency to detect performance degradation |
| RELIABILITY | DynamoDB | AWS/DynamoDB | ReplicationLatency | Reactive | Conditional | >= 1.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors replication latency for global tables |

### EC2

| Business Objectives | AWS Service | Namespace | Metric name | Reactive/Proactive | Metric Classification | Threshold | Recommended alarm configuration | Use case |
|---------------------|-------------|-----------|-------------|--------------------|-----------------------|-----------|---------------------------------|----------|
| RELIABILITY | EC2 | AWS/EC2 | StatusCheckFailed_Instance | Reactive | Native | >= 1.0 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = breaching | Reports whether the instance has passed the instance status check |
| RELIABILITY | EC2 | AWS/EC2 | StatusCheckFailed_System | Reactive | Native | >= 1.0 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = breaching | Reports whether the instance has passed the system status check |
| RELIABILITY | EC2 | AWS/EC2 | StatusCheckFailed_AttachedEBS | Reactive | Native | >= 1.0 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = breaching | Reports whether the instance has passed the attached EBS status check |

### EFS

| Business Objectives | AWS Service | Namespace | Metric name | Reactive/Proactive | Metric Classification | Threshold | Recommended alarm configuration | Use case |
|---------------------|-------------|-----------|-------------|--------------------|-----------------------|-----------|---------------------------------|----------|
| RELIABILITY | EFS | AWS/EFS | PercentIOLimit | Reactive | Native | >= 80.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = breaching | Shows how close a file system is to reaching the I/O limit of the General Purpose performance mode |

### EKS

| Business Objectives | AWS Service | Namespace | Metric name | Reactive/Proactive | Metric Classification | Threshold | Recommended alarm configuration | Use case |
|---------------------|-------------|-----------|-------------|--------------------|-----------------------|-----------|---------------------------------|----------|
| REACTIVE | EKS | ContainerInsights | pod_container_status_waiting_reason_crash_loop_back_off | Reactive | Native | > 1.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors containers stuck in CrashLoopBackOff |
| REACTIVE | EKS | ContainerInsights | pod_container_status_waiting_reason_create_container_config_error | Reactive | Native | > 1.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors containers with CreateContainerConfigError |
| REACTIVE | EKS | ContainerInsights | pod_container_status_waiting_reason_create_container_error | Reactive | Native | > 1.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors containers with CreateContainerError |
| REACTIVE | EKS | ContainerInsights | pod_container_status_waiting_reason_image_pull_error | Reactive | Native | > 1.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors containers with image pull errors |
| REACTIVE | EKS | ContainerInsights | pod_container_status_waiting_reason_start_error | Reactive | Native | > 1.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors containers with start errors |
| REACTIVE | EKS | ContainerInsights | cluster_failed_node_count | Reactive | Native | > 1.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors failed worker nodes in the EKS cluster |
| REACTIVE | EKS | ContainerInsights | pod_status_unknown | Reactive | Native | > 1.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors pods with unknown status |
| REACTIVE | EKS | ContainerInsights | apiserver_admission_webhook_admission_duration_seconds | Reactive | Non-native | > 1.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors admission webhook latency |
| PROACTIVE | EKS | ContainerInsights/Prometheus | apiserver_admission_controller_admission_duration_seconds | Reactive | Non-native | > 1.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors admission controller latency |
| PROACTIVE | EKS | ContainerInsights/Prometheus | apiserver_authorization_webhook_duration_seconds | Reactive | Non-native | > 1.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors authorization webhook duration |
| REACTIVE | EKS | ContainerInsights/Prometheus | apiserver_clusterip_repair_ip_errors_total | Reactive | Non-native | > 1.0 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors cluster IP repair errors |
| REACTIVE | EKS | ContainerInsights/Prometheus | apiserver_nodeport_repair_port_errors_total | Reactive | Non-native | > 1.0 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors node port repair errors |
| REACTIVE | EKS | ContainerInsights/Prometheus | kubelet_started_containers_errors_total | Reactive | Non-native | > 1.0 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors container start errors |
| REACTIVE | EKS | ContainerInsights/Prometheus | kubelet_runtime_operations_errors_total | Reactive | Non-native | > 1.0 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors kubelet runtime operation errors |
| REACTIVE | EKS | ContainerInsights/Prometheus | kubelet_started_pods_errors_total | Reactive | Non-native | > 1.0 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors pod start errors |
| REACTIVE | EKS | ContainerInsights/Prometheus | node_collector_zone_health | Reactive | Non-native | > 1.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors node health percentage per zone |

### ElastiCache

| Business Objectives | AWS Service | Namespace | Metric name | Reactive/Proactive | Metric Classification | Threshold | Recommended alarm configuration | Use case |
|---------------------|-------------|-----------|-------------|--------------------|-----------------------|-----------|---------------------------------|----------|
| PERFORMANCE | ElastiCache | AWS/ElastiCache | FreeableMemory | Reactive | Native | < 100000000 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors low freeable memory which can indicate spike in connections or high memory pressure |
| PERFORMANCE | ElastiCache | AWS/ElastiCache | DatabaseMemoryUsagePercentage | Reactive | Native | >= 90.0 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors the percentage of memory utilization for Redis clusters |
| PERFORMANCE | ElastiCache | AWS/ElastiCache | CurrConnections | Reactive | Native | > 1000 | Statistic = Maximum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors the number of client connections, excluding connections from read replicas |

### Elemental Media Services

| Business Objectives | AWS Service | Namespace | Metric name | Reactive/Proactive | Metric Classification | Threshold | Recommended alarm configuration | Use case |
|---------------------|-------------|-----------|-------------|--------------------|-----------------------|-----------|---------------------------------|----------|
| CUSTOMER_EXPERIENCE | Elemental Media Services | AWS/MediaLive | SvqTime | Reactive | Native | > 80.0 | Statistic = Maximum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Percentage of time MediaLive had to reduce quality optimizations to emit output in real time |
| RELIABILITY | Elemental Media Services | AWS/MediaPackage | EgressResponseTime | Reactive | Native | > 5000.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Time that it takes MediaPackage to process each output request |
| RELIABILITY | Elemental Media Services | AWS/MediaPackage | IngressResponseTime | Reactive | Native | > 5000.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Time that it takes MediaPackage to process each input request |

### Keyspaces

| Business Objectives | AWS Service | Namespace | Metric name | Reactive/Proactive | Metric Classification | Threshold | Recommended alarm configuration | Use case |
|---------------------|-------------|-----------|-------------|--------------------|-----------------------|-----------|---------------------------------|----------|
| RELIABILITY | Keyspaces | AWS/Cassandra | PerConnectionRequestRateExceeded | Reactive | Native | >= 1.0 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Tracks the requests that exceed the per-connection request rate quota |
| RELIABILITY | Keyspaces | AWS/Cassandra | ReadThrottleEvents | Reactive | Native | >= 1.0 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Tracks the requests that exceed the provisioned read capacity |
| RELIABILITY | Keyspaces | AWS/Cassandra | WriteThrottleEvents | Reactive | Native | >= 1.0 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Tracks the requests that exceed the provisioned write capacity |
| RELIABILITY | Keyspaces | AWS/Cassandra | ReplicationLatency | Reactive | Conditional | > 1000.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors the time it took to replicate updates, inserts, or deletes from one replica table to another replica table in a multi-Region keyspace |
| RELIABILITY | Keyspaces | AWS/Cassandra | StoragePartitionThroughputCapacityExceeded | Reactive | Native | >= 1.0 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Tracks the requests that exceed the throughput capacity of the storage partition |

### Kinesis

| Business Objectives | AWS Service | Namespace | Metric name | Reactive/Proactive | Metric Classification | Threshold | Recommended alarm configuration | Use case |
|---------------------|-------------|-----------|-------------|--------------------|-----------------------|-----------|---------------------------------|----------|
| RELIABILITY | Kinesis | AWS/Kinesis | ReadProvisionedThroughputExceeded | Proactive | Native | >= 1.0 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Tracks the number of times read operations exceed the provisioned read throughput capacity |
| RELIABILITY | Kinesis | AWS/Kinesis | WriteProvisionedThroughputExceeded | Proactive | Native | >= 1.0 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Identifies when write capacity limits are hit causing data ingestion delays or failures |
| RELIABILITY | Kinesis | AWS/Kinesis | GetRecords.IteratorAgeMilliseconds | Reactive | Native | > 600000.0 | Statistic = Maximum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Tracks how long records have been in the stream before being processed |
| RELIABILITY | Kinesis | AWS/Kinesis | PutRecords.FailedRecords | Reactive | Native | > 1.0 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Tracks the number of records that fail to be processed |
| RELIABILITY | Kinesis | AWS/Kinesis | PutRecords.ThrottledRecords | Proactive | Native | > 1.0 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors read throttling to detect capacity issues |

### Lambda

| Business Objectives | AWS Service | Namespace | Metric name | Reactive/Proactive | Metric Classification | Threshold | Recommended alarm configuration | Use case |
|---------------------|-------------|-----------|-------------|--------------------|-----------------------|-----------|---------------------------------|----------|
| RELIABILITY | Lambda | AWS/Lambda | (m1/m2)*100<br>m1 = Errors<br>m2 = Invocations | Reactive | Native | > 5.0 | Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors the ratio of errors to successful Lambda invocations |
| RELIABILITY | Lambda | AWS/Lambda | Throttles | Reactive | Native | >= 1.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors invocation request throughput and throttling |
| RELIABILITY | Lambda | AWS/Lambda | DeadLetterErrors | Reactive | Native | >= 1.0 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors when messages fail to reach the DLQ |
| RELIABILITY | Lambda | AWS/Lambda | ConcurrentExecutions | Reactive | Conditional | > 900.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Tracks the number of function instances running concurrently |

### RDS

| Business Objectives | AWS Service | Namespace | Metric name | Reactive/Proactive | Metric Classification | Threshold | Recommended alarm configuration | Use case |
|---------------------|-------------|-----------|-------------|--------------------|-----------------------|-----------|---------------------------------|----------|
| RELIABILITY | RDS | AWS/RDS | DiskQueueDepth | Reactive | Native | > 25.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors outstanding IOs waiting to be processed - identifies performance bottlenecks |
| RELIABILITY | RDS | AWS/RDS | FreeStorageSpace | Proactive | Native | < 2147483648.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = breaching | Proactively monitors available storage capacity to prevent database outages |
| RELIABILITY | RDS | AWS/RDS | ReplicaLag | Reactive | Conditional | > 30.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = breaching | Monitors replication lag times on RDS read replicas to ensure data freshness |
| LATENCY | RDS | AWS/RDS | ReadLatency | Reactive | Native | > 0.2 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors average time to read data from database storage |
| LATENCY | RDS | AWS/RDS | WriteLatency | Reactive | Native | > 0.2 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors average time to write data to database storage |

### Redshift

| Business Objectives | AWS Service | Namespace | Metric name | Reactive/Proactive | Metric Classification | Threshold | Recommended alarm configuration | Use case |
|---------------------|-------------|-----------|-------------|--------------------|-----------------------|-----------|---------------------------------|----------|
| RELIABILITY | Redshift | AWS/Redshift | DatabaseConnections | Reactive | Native | > 90.0 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = breaching | Tracks the number of database connections to a cluster |
| RELIABILITY | Redshift | AWS/Redshift | HealthStatus | Reactive | Native | < 1.0 | Statistic = Minimum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = breaching | Indicates the health of the cluster |
| RELIABILITY | Redshift | AWS/Redshift | PercentageDiskSpaceUsed | Reactive | Native | > 95.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = breaching | Tracks the percent of disk space used |
| LATENCY | Redshift | AWS/Redshift | ReadLatency | Reactive | Native | > 20.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Tracks the average amount of time taken for disk read I/O operations |
| LATENCY | Redshift | AWS/Redshift | WriteLatency | Reactive | Native | > 20.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Tracks the average amount of time taken for disk write I/O operations |

### S3

| Business Objectives | AWS Service | Namespace | Metric name | Reactive/Proactive | Metric Classification | Threshold | Recommended alarm configuration | Use case |
|---------------------|-------------|-----------|-------------|--------------------|-----------------------|-----------|---------------------------------|----------|
| PERFORMANCE | S3 | AWS/S3 | TotalRequestLatency | Reactive | Conditional | > 1000.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Measures the total time taken to process requests to an S3 bucket |

### SNS

| Business Objectives | AWS Service | Namespace | Metric name | Reactive/Proactive | Metric Classification | Threshold | Recommended alarm configuration | Use case |
|---------------------|-------------|-----------|-------------|--------------------|-----------------------|-----------|---------------------------------|----------|
| RELIABILITY | SNS | AWS/SNS | NumberOfNotificationsFailed | Reactive | Native | >= 5.0 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors failed notifications to detect delivery issues |
| RELIABILITY | SNS | AWS/SNS | NumberOfNotificationsFilteredOut-InvalidAttributes | Reactive | Conditional | >= 1.0 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = breaching | Monitors notifications filtered due to invalid attributes |
| RELIABILITY | SNS | AWS/SNS | NumberOfNotificationsFilteredOut-NoMessageAttributes | Reactive | Conditional | >= 1.0 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = breaching | Monitors notifications filtered due to missing message attributes |
| RELIABILITY | SNS | AWS/SNS | NumberOfNotificationsFilteredOut-InvalidMessageBody | Reactive | Conditional | >= 1.0 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = breaching | Monitors notifications filtered due to invalid message body |
| RELIABILITY | SNS | AWS/SNS | NumberOfNotificationsRedrivenToDlq | Reactive | Conditional | >= 1.0 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = breaching | Monitors notifications redirected to a Dead Letter Queue |
| RELIABILITY | SNS | AWS/SNS | SMSSuccessRate | Reactive | Conditional | < 90.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors the rate of successful SMS message deliveries |

### SQS

| Business Objectives | AWS Service | Namespace | Metric name | Reactive/Proactive | Metric Classification | Threshold | Recommended alarm configuration | Use case |
|---------------------|-------------|-----------|-------------|--------------------|-----------------------|-----------|---------------------------------|----------|
| RELIABILITY | SQS | AWS/SQS | ApproximateNumberOfMessagesVisible | Reactive | Native | >= 1000.0 | Statistic = Average<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors the number of visible messages in the SQS queue that are awaiting processing |
| RELIABILITY | SQS | AWS/SQS | ApproximateAgeOfOldestMessage | Reactive | Native | >= 900.0 | Statistic = Maximum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = breaching | Measures the duration that the oldest message has been in the queue without being processed |

### Step Functions

| Business Objectives | AWS Service | Namespace | Metric name | Reactive/Proactive | Metric Classification | Threshold | Recommended alarm configuration | Use case |
|---------------------|-------------|-----------|-------------|--------------------|-----------------------|-----------|---------------------------------|----------|
| RELIABILITY | Step Functions | AWS/States | ExecutionsFailed | Reactive | Native | >= 5.0 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors failed executions to detect workflow issues |
| RELIABILITY | Step Functions | AWS/States | ExecutionsTimedOut | Reactive | Native | >= 1.0 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Monitors timed out executions to detect timeout issues |
| LATENCY | Step Functions | AWS/States | ExecutionThrottled | Reactive | Native | >= 1.0 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = notBreaching | Tracks executions throttled due to exceeding AWS service limits |

### VPC Transit Gateway

| Business Objectives | AWS Service | Namespace | Metric name | Reactive/Proactive | Metric Classification | Threshold | Recommended alarm configuration | Use case |
|---------------------|-------------|-----------|-------------|--------------------|-----------------------|-----------|---------------------------------|----------|
| RELIABILITY | VPC Transit Gateway | AWS/TransitGateway | BytesDropCountBlackhole | Reactive | Native | > 1000000.0 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = breaching | Number of bytes dropped because they matched a blackhole route |
| RELIABILITY | VPC Transit Gateway | AWS/TransitGateway | BytesDropCountNoRoute | Reactive | Native | > 1000000.0 | Statistic = Sum<br>Period = 60 seconds<br>DatapointsToAlarm = 5<br>TreatMissingData = breaching | Number of bytes dropped because they did not match a route |
