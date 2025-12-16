from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List

from botocore.exceptions import ClientError
from injector import inject
from mypy_boto3_cloudwatch.type_defs import MetricAlarmTypeDef

from aws_idr_customer_cli.clients.s3 import BotoS3Manager
from aws_idr_customer_cli.clients.sts import BotoStsManager
from aws_idr_customer_cli.core.interactive.ui import InteractiveUI
from aws_idr_customer_cli.data_accessors.alarm_accessor import AlarmAccessor
from aws_idr_customer_cli.exceptions import LimitExceededError
from aws_idr_customer_cli.models.alarm_models import AlarmRecommendation
from aws_idr_customer_cli.services.create_alarm.alarm_recommendation_service import (
    AlarmRecommendationService,
)
from aws_idr_customer_cli.services.file_cache.data import (
    AlarmConfiguration,
    AlarmContacts,
    AlarmCreation,
    OnboardingAlarm,
    ResourceArn,
)
from aws_idr_customer_cli.utils.arn_utils import (
    build_resource_arn_object,
    extract_resource_id_from_arn,
)
from aws_idr_customer_cli.utils.constants import Region
from aws_idr_customer_cli.utils.log_handlers import CliLogger

S3_IDENTIFIER = ":s3:::"


class AlarmService:
    """Alarm service implementation."""

    IDR_ALARM_PREFIX = "IDR-"

    @inject
    def __init__(
        self,
        accessor: AlarmAccessor,
        logger: CliLogger,
        alarm_recommendation_service: AlarmRecommendationService,
        sts_manager: BotoStsManager,
        s3_manager: BotoS3Manager,
        ui: InteractiveUI,
    ) -> None:
        self.accessor = accessor
        self.logger = logger
        self.alarm_recommendation_service = alarm_recommendation_service
        self.sts_manager = sts_manager
        self.s3_manager = s3_manager
        self.ui = ui

    def create_alarm(self, recommendation: AlarmRecommendation) -> AlarmCreation:
        """
        Create CloudWatch alarm from recommendation object.

        Args:
            recommendation: AlarmRecommendation object containing all alarm configuration

        Returns:
            AlarmCreation object with creation result
        """
        alarm_name = recommendation.alarm_name
        region = recommendation.resource_arn.region

        # Convert to CloudWatch API format
        recommendation_dict = recommendation.to_cloudwatch_dict()

        self.logger.info(
            f"Creating alarm '{alarm_name}' in region '{region}' "
            f"with configuration: {recommendation_dict}"
        )

        self.accessor.create_alarm(alarm_config=recommendation_dict, region=region)

        self.logger.info(
            f"Successfully created alarm '{alarm_name}' in region '{region}'"
        )

        alarm = self.recommendation_to_alarm_creation_object(recommendation)
        alarm.successful = True
        alarm.created_at = datetime.now(timezone.utc)

        return alarm

    def get_existing_idr_alarms(
        self, regions: set[str]
    ) -> Dict[str, MetricAlarmTypeDef]:
        """
        Get all IDR alarms in specified region as a lookup dictionary for efficient
        existence checks.
        """

        all_alarms = {}

        for region in regions:
            alarms = self.accessor.list_alarms_by_prefix(self.IDR_ALARM_PREFIX, region)
            # Update dictionary with alarms from this region
            all_alarms.update({alarm["AlarmName"]: alarm for alarm in alarms})

        return all_alarms

    def flag_existing_alarms_for_duplication(
        self, recommendations: List[AlarmRecommendation]
    ) -> List[AlarmRecommendation]:
        """
        Check alarm recommendations against existing IDR alarms and flag duplicates.

        Compares the alarm_name field of each recommendation against all existing IDR alarms
        in the customer account region. Updates the already_exists field of each
        recommendation indicating whether an alarm with that name already exists.

        Args:
            recommendations: List of AlarmRecommendation objects

        Returns:
            Updated recommendations with already_exists field set.
            True indicates the alarm already exists, False indicates it's new.

        Note:
            Uses O(1) lookup via dictionary keys for efficient duplicate detection.
        """
        # Extract regions from resource_arn's in the recommendation objects
        regions = set(
            recommendation.resource_arn.region for recommendation in recommendations
        )

        existing_alarms = self.get_existing_idr_alarms(regions=regions)

        for recommendation in recommendations:
            recommendation.already_exists = recommendation.alarm_name in existing_alarms

        return recommendations

    def _log_batch_progress(
        self,
        total_count: int,
        processed_count: int,
        created_count: int,
        failed_count: int,
    ) -> None:
        self.ui.display_info(
            f"Progress: {processed_count} out of {total_count} alarms processed "
            f"({created_count} created, {failed_count} failed)"
        )

    def _process_single_alarm_creation(
        self, recommendation: AlarmRecommendation
    ) -> AlarmCreation:
        try:
            return self.create_alarm(recommendation=recommendation)
        except ClientError as e:
            if e.response["Error"]["Code"] == "LimitExceeded":
                self.ui.display_error(
                    "CloudWatch alarm limit exceeded. Unable to create remaining alarms."
                )
                raise LimitExceededError
            else:
                self.ui.display_error(
                    f"Failed to create alarm '{recommendation.alarm_name}': {e}"
                )
                raise
        except Exception as e:
            self.ui.display_error(
                f"Failed to create alarm '{recommendation.alarm_name}': {e}"
            )
            raise

    def create_alarms_from_recommendations(
        self,
        recommendations: List[AlarmRecommendation],
        batch_size: int = 20,
    ) -> Dict[str, List[AlarmCreation]]:
        """Create alarms from recommendations, skipping those that already exist."""
        unselected_recommendations = [r for r in recommendations if not r.is_selected]
        selected_recommendations = [r for r in recommendations if r.is_selected]
        flagged_recommendations = self.flag_existing_alarms_for_duplication(
            selected_recommendations
        )
        existing_alarms = [r for r in flagged_recommendations if r.already_exists]
        new_recommendations = [
            r for r in flagged_recommendations if not r.already_exists
        ]

        created_alarms = []
        failed_alarms = []
        total_count = len(new_recommendations)
        created_count = 0
        failed_count = 0
        limit_exceeded = False

        self.ui.display_info("🔍 Checking alarm creation status...")
        for i in range(0, total_count, batch_size):
            self._log_batch_progress(total_count, i, created_count, failed_count)
            batch = new_recommendations[i : i + batch_size]
            for j, recommendation in enumerate(batch):
                try:
                    alarm_creation = self._process_single_alarm_creation(recommendation)
                    created_alarms.append(alarm_creation)
                    created_count += 1
                except LimitExceededError:
                    limit_exceeded = True
                    remaining_recommendation = new_recommendations[i + j :]
                    failed_alarms.extend(remaining_recommendation)
                    failed_count += len(remaining_recommendation)
                    break
                except Exception:
                    failed_alarms.append(recommendation)
                    failed_count += 1
            if limit_exceeded:
                break

        # Convert all results to AlarmCreation objects
        unselected_alarms_converted = self.recommendations_to_alarm_creation_objects(
            unselected_recommendations
        )
        existing_alarms_converted = self.recommendations_to_alarm_creation_objects(
            existing_alarms
        )

        # For failed alarms, convert and mark as unsuccessful
        failed_alarms_converted = self.recommendations_to_alarm_creation_objects(
            failed_alarms
        )
        for alarm in failed_alarms_converted:
            alarm.successful = False

        self.logger.info(
            f"Alarm creation complete: {created_count} created, {failed_count} failed"
        )
        return {
            "unselected_alarms": unselected_alarms_converted,
            "created_alarms": created_alarms,
            "failed_alarms": failed_alarms_converted,
            "existing_alarms": existing_alarms_converted,
        }

    def generate_alarm_recommendations(
        self, resource_arns: List[ResourceArn]
    ) -> List[AlarmRecommendation]:
        """
        Generate alarm recommendations for resources using resource-level processing.

        Returns:
            List of alarm recommendations ready for MLO selection
        """
        if not resource_arns:
            self.logger.warning(
                "No resource ARNs provided for alarm recommendation generation"
            )
            return []

        self.logger.info(
            f"Processing {len(resource_arns)} resources individually for maximum resilience"
        )

        all_recommendations = []
        processed_count = 0
        failed_count = 0

        for resource in resource_arns:
            try:
                # Process single resource (template caching makes this efficient)
                alarm_configs = (
                    self.alarm_recommendation_service.generate_alarm_configurations(
                        [resource]
                    )
                )

                if alarm_configs:
                    recommendations = self._convert_configs_to_recommendations(
                        alarm_configs
                    )
                    all_recommendations.extend(recommendations)
                    processed_count += 1
                else:
                    # Check if this is EKS/ECS resource for better error message
                    if ":eks:" in resource.arn or ":ecs:" in resource.arn:
                        service_name = "EKS" if ":eks:" in resource.arn else "ECS"
                        self.logger.warning(
                            f"No configurations generated for resource: {resource.arn} "
                            f"(Container Insights not enabled - required for {service_name} alarms)"
                        )
                    failed_count += 1

            except Exception as e:
                self.logger.error(
                    f"Failed to process resource {resource.arn}: {str(e)}"
                )
                failed_count += 1
                continue  # Continue with other resources

        self.logger.info(
            f"Resource processing complete: {processed_count} successful, {failed_count} failed, "
            f"{len(all_recommendations)} total Alarm recommendations generated"
        )

        return all_recommendations

    def _convert_configs_to_recommendations(
        self, alarm_configs: List[Dict[str, Any]]
    ) -> List[AlarmRecommendation]:
        """
        Convert alarm template configurations to AlarmRecommendations.

        Args:
            alarm_configs: List of configurations from AlarmTemplateService

        Returns:
            List of AlarmRecommendations
        """
        recommendations = []

        for config in alarm_configs:
            try:
                template_config = config.get("template_config", {})

                if not template_config:
                    self.logger.warning(
                        f"No template_config found for alarm: {config.get('alarm_name', 'Unknown')}"
                    )
                    continue

                # Use the AlarmName from template_config
                # if available (already has placeholders replaced),
                # otherwise fall back to constructing it from template name + resource_id
                if "AlarmName" in template_config:
                    alarm_name = template_config["AlarmName"]
                else:
                    resource_id = extract_resource_id_from_arn(config["resource_arn"])
                    alarm_name = f"{config['alarm_name']}-{resource_id}"

                # Check if this is a math expression alarm (has Metrics field)
                has_metrics = "Metrics" in template_config

                recommendation = AlarmRecommendation(
                    alarm_name=alarm_name,
                    already_exists=None,
                    resource_arn=build_resource_arn_object(config["resource_arn"]),
                    is_selected=True,
                    alarm_description=template_config.get(
                        "AlarmDescription", config.get("description", "")
                    ),
                    metric_name=template_config.get("MetricName"),
                    namespace=template_config.get("Namespace"),
                    statistic=template_config.get("Statistic"),
                    threshold=template_config.get("Threshold"),
                    comparison_operator=template_config.get("ComparisonOperator"),
                    evaluation_periods=template_config.get("EvaluationPeriods", 2),
                    period=template_config.get("Period", 300),
                    datapoints_to_alarm=template_config.get("DatapointsToAlarm"),
                    treat_missing_data=template_config.get(
                        "TreatMissingData", "notBreaching"
                    ),
                    dimensions=template_config.get("Dimensions", []),
                    alarm_type=config.get("alarm_type"),
                    tags=config.get("tags", {}),
                    metrics=template_config.get("Metrics") if has_metrics else None,
                )

                # Different validation for math expression vs simple metric alarms
                if has_metrics:
                    # For math expression alarms, only require threshold and comparison_operator
                    required_params = ["threshold", "comparison_operator"]
                else:
                    # For simple metric alarms, require the traditional fields
                    required_params = [
                        "metric_name",
                        "namespace",
                        "statistic",
                        "threshold",
                        "comparison_operator",
                    ]

                missing_params = [
                    param
                    for param in required_params
                    if not getattr(recommendation, param, None)
                ]

                if missing_params:
                    self.logger.error(
                        f"Missing required parameters for alarm '{config['alarm_name']}': "
                        f"{missing_params}"
                    )
                    continue

                recommendations.append(recommendation)

            except Exception as e:
                self.logger.error(
                    f"Failed to convert config to recommendation: {str(e)}"
                )
                continue

        self.logger.info(
            f"Converted {len(recommendations)} configurations to recommendations"
        )
        return recommendations

    def _get_alarm_region(self, resource_arn: str) -> str:
        """
        Determine the appropriate CloudWatch region for creating alarms based on resource type.

        For S3 buckets, retrieves the actual bucket region since S3 is a global service.
        For all other resources, returns us-east-1 as the default CloudWatch region.
        """
        if S3_IDENTIFIER in resource_arn:
            # Extract bucket name and get actual region
            bucket_name = resource_arn.split(":")[-1]
            response = self.s3_manager.get_bucket_location(bucket_name=bucket_name)
            return str(response)
        else:
            return str(Region.US_EAST_1.value)

    def recommendation_to_alarm_creation_object(
        self, recommendation: AlarmRecommendation
    ) -> AlarmCreation:
        """
        Convert AlarmRecommendation to AlarmCreation object.

        Args:
            recommendation: AlarmRecommendation object

        Returns:
            AlarmCreation object
        """
        account_id = self.sts_manager.retrieve_account_id_from_sts()
        region = recommendation.resource_arn.region
        alarm_region = (
            self._get_alarm_region(resource_arn=recommendation.resource_arn.arn)
            if region == Region.GLOBAL_REGION.value
            else region
        )
        alarm_arn = (
            f"arn:aws:"
            f"cloudwatch:{alarm_region}:"
            f"{account_id}:alarm:{recommendation.alarm_name}"
        )

        return AlarmCreation(
            alarm_arn=alarm_arn,
            is_selected=recommendation.is_selected,
            already_exists=recommendation.already_exists,
            created_at=None,  # Will be populated after creation
            resource_arn=recommendation.resource_arn,
            alarm_configuration=AlarmConfiguration(
                alarm_name=recommendation.alarm_name
            ),
            successful=None,  # Will be populated after creation
        )

    def alarm_creation_object_to_recommendation(
        self, alarm: AlarmCreation
    ) -> AlarmRecommendation:
        """
        Convert AlarmCreation object back to AlarmRecommendation.

        Args:
            alarm: AlarmCreation object

        Returns:
            AlarmRecommendation object
        """
        return self.alarm_creation_objects_to_recommendations([alarm])[0]

    def recommendations_to_alarm_creation_objects(
        self, recommendations: List[AlarmRecommendation]
    ) -> List[AlarmCreation]:
        return [
            self.recommendation_to_alarm_creation_object(rec) for rec in recommendations
        ]

    def alarm_creation_objects_to_recommendations(
        self, alarms: List[AlarmCreation]
    ) -> List[AlarmRecommendation]:
        """Convert AlarmCreation objects to AlarmRecommendations."""
        if not alarms:
            return []

        # Group alarms by resource ARN to minimize config regeneration
        alarms_by_resource = defaultdict(list)
        for alarm in alarms:
            alarms_by_resource[alarm.resource_arn.arn].append(alarm)

        recommendations = []

        for resource_arn_str, resource_alarms in alarms_by_resource.items():
            # Generate configs once per resource instead of once per alarm
            # Suppress warnings to avoid duplicate messages (already shown in step 8)
            alarm_configs = (
                self.alarm_recommendation_service.generate_alarm_configurations(
                    [resource_alarms[0].resource_arn], suppress_warnings=True
                )
            )

            # Use dictionary for O(1) lookup instead of O(n) search
            config_lookup = {
                config.get("template_config", {}).get("AlarmName", ""): config
                for config in alarm_configs
            }

            for alarm in resource_alarms:
                stored_alarm_name = alarm.alarm_configuration.alarm_name
                matching_config = config_lookup.get(stored_alarm_name)

                if not matching_config:
                    available_names = list(config_lookup.keys())
                    self.logger.error(
                        f"Could not find matching alarm configuration for '{stored_alarm_name}'. "
                        f"Available alarm names: {available_names}"
                    )
                    raise ValueError(
                        f"Could not find alarm configuration "
                        f"matching stored alarm name: {stored_alarm_name}"
                    )

                # Convert config back to AlarmRecommendation
                recs = self._convert_configs_to_recommendations([matching_config])

                if len(recs) != 1:
                    raise ValueError(
                        f"Failed to convert configuration "
                        f"to recommendation for alarm: {stored_alarm_name}"
                    )

                recommendation = recs[0]
                recommendation.is_selected = alarm.is_selected
                recommendation.already_exists = alarm.already_exists
                recommendations.append(recommendation)

        return recommendations

    def convert_created_alarms_to_onboarding_alarms(
        self, created_alarms: List[AlarmCreation], alarm_contacts: AlarmContacts
    ) -> List[OnboardingAlarm]:
        self.ui.display_info(
            f"Associating above contact information with {len(created_alarms)} alarms"
        )
        return [
            OnboardingAlarm(
                alarm_arn=alarm.alarm_arn,
                primary_contact=alarm_contacts.primary_contact,
                escalation_contact=alarm_contacts.escalation_contact,
            )
            for alarm in created_alarms
            if alarm.alarm_arn
        ]
