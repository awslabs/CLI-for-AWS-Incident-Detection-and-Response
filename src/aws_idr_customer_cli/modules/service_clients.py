import injector

from aws_idr_customer_cli.clients.s3 import BotoS3Manager
from aws_idr_customer_cli.clients.sts import BotoStsManager
from aws_idr_customer_cli.core.interactive.ui import InteractiveUI
from aws_idr_customer_cli.data_accessors.alarm_accessor import AlarmAccessor
from aws_idr_customer_cli.data_accessors.resource_tagging_accessor import (
    ResourceTaggingAccessor,
)
from aws_idr_customer_cli.data_accessors.support_case_accessor import (
    SupportCaseAccessor,
)
from aws_idr_customer_cli.interfaces.file_cache_service import FileCacheServiceInterface
from aws_idr_customer_cli.services.create_alarm.alarm_recommendation_service import (
    AlarmRecommendationService,
)
from aws_idr_customer_cli.services.create_alarm.alarm_service import AlarmService
from aws_idr_customer_cli.services.input_module.resource_finder_service import (
    ResourceFinderService,
)
from aws_idr_customer_cli.services.support_case_service import SupportCaseService
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
        s3_manager: BotoS3Manager,
        ui: InteractiveUI,
    ) -> AlarmService:
        return AlarmService(
            accessor=accessor,
            logger=logger,
            alarm_recommendation_service=alarm_recommendation_service,
            sts_manager=sts_manager,
            s3_manager=s3_manager,
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
    def provide_metric_namespace_validator(
        self, alarm_accessor: AlarmAccessor
    ) -> MetricNamespaceValidator:
        return MetricNamespaceValidator(alarm_accessor=alarm_accessor)

    @injector.singleton
    @injector.provider
    def provide_alarm_recommendation_service(
        self,
        logger: CliLogger,
        namespace_validator: MetricNamespaceValidator,
    ) -> AlarmRecommendationService:
        return AlarmRecommendationService(
            logger=logger,
            namespace_validator=namespace_validator,
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
