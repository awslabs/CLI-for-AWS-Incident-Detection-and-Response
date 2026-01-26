import injector

from aws_idr_customer_cli.clients.sts import BotoStsManager
from aws_idr_customer_cli.core.interactive.ui import InteractiveUI
from aws_idr_customer_cli.data_accessors.alarm_accessor import AlarmAccessor
from aws_idr_customer_cli.data_accessors.apigateway_accessor import ApiGatewayAccessor
from aws_idr_customer_cli.data_accessors.cloudformation_accessor import (
    CloudFormationAccessor,
)
from aws_idr_customer_cli.data_accessors.cloudfront_accessor import (
    CloudFrontAccessor,
)
from aws_idr_customer_cli.data_accessors.cloudwatch_metrics_accessor import (
    CloudWatchMetricsAccessor,
)
from aws_idr_customer_cli.data_accessors.dynamodb_accessor import DynamoDbAccessor
from aws_idr_customer_cli.data_accessors.eventbridge_accessor import EventBridgeAccessor
from aws_idr_customer_cli.data_accessors.keyspaces_accessor import KeyspacesAccessor
from aws_idr_customer_cli.data_accessors.lambda_accessor import LambdaAccessor
from aws_idr_customer_cli.data_accessors.logs_accessor import LogsAccessor
from aws_idr_customer_cli.data_accessors.rds_accessor import RdsAccessor
from aws_idr_customer_cli.data_accessors.resource_tagging_accessor import (
    ResourceTaggingAccessor,
)
from aws_idr_customer_cli.data_accessors.s3_accessor import S3Accessor
from aws_idr_customer_cli.data_accessors.sns_accessor import SnsAccessor
from aws_idr_customer_cli.data_accessors.support_case_accessor import (
    SupportCaseAccessor,
)
from aws_idr_customer_cli.interfaces.file_cache_service import FileCacheServiceInterface
from aws_idr_customer_cli.services.apm.apm_service import ApmService
from aws_idr_customer_cli.services.apm.cfn_stack_processor import CfnTemplateProcessor
from aws_idr_customer_cli.services.create_alarm.alarm_recommendation_service import (
    AlarmRecommendationService,
)
from aws_idr_customer_cli.services.create_alarm.alarm_service import AlarmService
from aws_idr_customer_cli.services.create_alarm.lambda_edge_detection_service import (
    LambdaEdgeDetectionService,
)
from aws_idr_customer_cli.services.create_alarm.lambda_edge_processor import (
    LambdaEdgeProcessor,
)
from aws_idr_customer_cli.services.input_module.resource_finder_service import (
    ResourceFinderService,
)
from aws_idr_customer_cli.services.support_case_service import SupportCaseService
from aws_idr_customer_cli.utils.create_alarm.conditional_metric_validator import (
    ConditionalMetricValidator,
)
from aws_idr_customer_cli.utils.create_alarm.metric_namespace_validator import (
    MetricNamespaceValidator,
)
from aws_idr_customer_cli.utils.log_handlers import CliLogger
from aws_idr_customer_cli.utils.validate_alarm.alarm_validator import AlarmValidator


class ServiceClientsModule(injector.Module):
    @injector.singleton
    @injector.provider
    def provide_alarm_service(
        self,
        accessor: AlarmAccessor,
        logger: CliLogger,
        alarm_recommendation_service: AlarmRecommendationService,
        sts_manager: BotoStsManager,
        s3_accessor: S3Accessor,
        ui: InteractiveUI,
    ) -> AlarmService:
        return AlarmService(
            accessor=accessor,
            logger=logger,
            alarm_recommendation_service=alarm_recommendation_service,
            sts_manager=sts_manager,
            s3_accessor=s3_accessor,
            ui=ui,
        )

    @injector.singleton
    @injector.provider
    def provide_resource_finder_service(
        self,
        accessor: ResourceTaggingAccessor,
        interactive_ui: InteractiveUI,
    ) -> ResourceFinderService:
        return ResourceFinderService(accessor=accessor, ui=interactive_ui)

    @injector.singleton
    @injector.provider
    def provide_support_service(
        self,
        accessor: SupportCaseAccessor,
        logger: CliLogger,
        file_cache_service: FileCacheServiceInterface,
    ) -> SupportCaseService:
        return SupportCaseService(
            accessor=accessor, logger=logger, file_cache_service=file_cache_service
        )

    @injector.singleton
    @injector.provider
    def provide_conditional_metric_validator(
        self,
        alarm_accessor: AlarmAccessor,
        sns_accessor: SnsAccessor,
        lambda_accessor: LambdaAccessor,
        dynamodb_accessor: DynamoDbAccessor,
        rds_accessor: RdsAccessor,
        s3_accessor: S3Accessor,
        keyspaces_accessor: KeyspacesAccessor,
    ) -> ConditionalMetricValidator:
        """Provide ConditionalMetricValidator with service-specific accessors."""
        return ConditionalMetricValidator(
            alarm_accessor=alarm_accessor,
            sns_accessor=sns_accessor,
            lambda_accessor=lambda_accessor,
            dynamodb_accessor=dynamodb_accessor,
            rds_accessor=rds_accessor,
            s3_accessor=s3_accessor,
            keyspaces_accessor=keyspaces_accessor,
        )

    @injector.singleton
    @injector.provider
    def provide_metric_namespace_validator(
        self,
        metrics_accessor: CloudWatchMetricsAccessor,
        conditional_validator: ConditionalMetricValidator,
    ) -> MetricNamespaceValidator:
        return MetricNamespaceValidator(
            metrics_accessor=metrics_accessor,
            conditional_validator=conditional_validator,
        )

    @injector.singleton
    @injector.provider
    def provide_lambda_edge_processor(
        self,
        logger: CliLogger,
        metrics_accessor: CloudWatchMetricsAccessor,
    ) -> LambdaEdgeProcessor:
        return LambdaEdgeProcessor(
            logger=logger,
            metrics_accessor=metrics_accessor,
        )

    @injector.singleton
    @injector.provider
    def provide_lambda_edge_detection_service(
        self,
        logger: CliLogger,
        cloudfront_accessor: CloudFrontAccessor,
    ) -> LambdaEdgeDetectionService:
        return LambdaEdgeDetectionService(
            logger=logger,
            cloudfront_accessor=cloudfront_accessor,
        )

    @injector.singleton
    @injector.provider
    def provide_alarm_recommendation_service(
        self,
        logger: CliLogger,
        namespace_validator: MetricNamespaceValidator,
        apigateway_accessor: ApiGatewayAccessor,
        lambda_edge_detection_service: LambdaEdgeDetectionService,
        metrics_accessor: CloudWatchMetricsAccessor,
        lambda_edge_processor: LambdaEdgeProcessor,
        ui: InteractiveUI,
    ) -> AlarmRecommendationService:
        return AlarmRecommendationService(
            logger=logger,
            namespace_validator=namespace_validator,
            apigateway_accessor=apigateway_accessor,
            lambda_edge_detection_service=lambda_edge_detection_service,
            metrics_accessor=metrics_accessor,
            lambda_edge_processor=lambda_edge_processor,
            ui=ui,
        )

    @injector.singleton
    @injector.provider
    def provide_alarm_validator(
        self,
        logger: CliLogger,
        alarm_accessor: AlarmAccessor,
    ) -> AlarmValidator:
        return AlarmValidator(
            logger=logger,
            alarm_accessor=alarm_accessor,
        )

    @injector.singleton
    @injector.provider
    def provide_template_processor(self) -> CfnTemplateProcessor:
        return CfnTemplateProcessor()

    @injector.singleton
    @injector.provider
    def provide_apm_service(
        self,
        cloudformation_accessor: CloudFormationAccessor,
        eventbridge_accessor: EventBridgeAccessor,
        sns_accessor: SnsAccessor,
        logs_accessor: LogsAccessor,
        metrics_accessor: CloudWatchMetricsAccessor,
        logger: CliLogger,
        ui: InteractiveUI,
    ) -> ApmService:
        return ApmService(
            cloudformation_accessor=cloudformation_accessor,
            eventbridge_accessor=eventbridge_accessor,
            sns_accessor=sns_accessor,
            logs_accessor=logs_accessor,
            metrics_accessor=metrics_accessor,
            logger=logger,
            ui=ui,
        )
