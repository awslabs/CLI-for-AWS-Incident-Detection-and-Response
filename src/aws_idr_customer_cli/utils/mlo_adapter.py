from typing import Callable, List, TypeVar

from aws_idr_customer_cli.exceptions import MloAdapterTypeError
from aws_idr_customer_cli.models.alarm_models import AlarmRecommendation
from aws_idr_customer_cli.models.mlo_selection_manager import MloItem
from aws_idr_customer_cli.services.file_cache.data import ResourceArn

T = TypeVar("T")


class MloAdapter:
    # Generic list conversion methods
    @staticmethod
    def objects_to_mlo_items(
        objects: List[T], converter: Callable[[T], MloItem]
    ) -> List[MloItem]:
        """Convert a list of objects to MloItems using the provided converter function."""
        return [converter(obj) for obj in objects]

    @staticmethod
    def mlo_items_to_objects(
        mlo_items: List[MloItem],
        converter: Callable[[MloItem], T],
        filter_selected: bool = False,
    ) -> List[T]:
        """Convert a list of MloItems to objects using the provided converter function."""
        items_to_convert = (
            [item for item in mlo_items if item.selected]
            if filter_selected
            else mlo_items
        )
        return [converter(item) for item in items_to_convert]

    # AlarmRecommendation conversions
    @staticmethod
    def alarm_recommendation_to_mlo_item(
        alarm_recommendation: AlarmRecommendation,
    ) -> MloItem:
        alarm_details = alarm_recommendation.alarm_configuration_to_formatted_string()

        return MloItem(
            id=alarm_recommendation.resource_arn.arn,
            group=alarm_recommendation.resource_arn.type,
            friendly_name=alarm_recommendation.alarm_name,
            region=alarm_recommendation.resource_arn.region,
            details=alarm_details,
            selected=False,
            source_data=alarm_recommendation,
        )

    @staticmethod
    def mlo_item_to_alarm_recommendation(mlo_item: MloItem) -> AlarmRecommendation:
        if not isinstance(mlo_item.source_data, AlarmRecommendation):
            raise MloAdapterTypeError(
                f"MLO Item incompatible, expected AlarmRecommendation, "
                f"got {type(mlo_item.source_data).__name__}"
            )
        alarm_recommendation: AlarmRecommendation = mlo_item.source_data
        alarm_recommendation.is_selected = mlo_item.selected
        return alarm_recommendation

    @staticmethod
    def alarm_recommendations_to_mlo_items(
        alarm_recommendations: List[AlarmRecommendation],
    ) -> List[MloItem]:
        return MloAdapter.objects_to_mlo_items(
            alarm_recommendations, MloAdapter.alarm_recommendation_to_mlo_item
        )

    @staticmethod
    def mlo_items_to_alarm_recommendations(
        mlo_items: List[MloItem],
    ) -> List[AlarmRecommendation]:
        return MloAdapter.mlo_items_to_objects(
            mlo_items, MloAdapter.mlo_item_to_alarm_recommendation
        )

    # ResourceArn conversions
    @staticmethod
    def _create_friendly_resource_name(arn: str) -> str:
        """Create a user-friendly name from ARN."""
        if "/" in arn:
            return arn.split("/")[-1]
        elif ":" in arn:
            return arn.split(":")[-1]
        return arn

    @staticmethod
    def resource_arn_to_mlo_item(resource_arn: ResourceArn) -> MloItem:
        # Use Name tag if available, otherwise fall back to generated friendly name
        display_name = resource_arn.name or MloAdapter._create_friendly_resource_name(
            resource_arn.arn
        )

        # Build details with non-redundant information
        details_parts = [f"Region: {resource_arn.region}"]

        if resource_arn.name:
            # Show the ARN-derived name for additional context only if it differs from the name tag
            arn_derived_name = MloAdapter._create_friendly_resource_name(
                resource_arn.arn
            )
            if arn_derived_name != resource_arn.name:
                details_parts.append(f"Resource ID: {arn_derived_name}")

        details = " | ".join(details_parts)

        return MloItem(
            id=resource_arn.arn,
            group=resource_arn.type,
            region=resource_arn.region,
            friendly_name=display_name,
            details=details,
            source_data=resource_arn,
        )

    @staticmethod
    def mlo_item_to_resource_arn(mlo_item: MloItem) -> ResourceArn:
        if not isinstance(mlo_item.source_data, ResourceArn):
            raise MloAdapterTypeError(
                f"MLO Item incompatible, expected ResourceArn, "
                f"got {type(mlo_item.source_data).__name__}"
            )
        return mlo_item.source_data

    @staticmethod
    def resource_arns_to_mlo_items(resource_arns: List[ResourceArn]) -> List[MloItem]:
        return MloAdapter.objects_to_mlo_items(
            resource_arns, MloAdapter.resource_arn_to_mlo_item
        )

    @staticmethod
    def mlo_items_to_resource_arns(mlo_items: List[MloItem]) -> List[ResourceArn]:
        return MloAdapter.mlo_items_to_objects(
            mlo_items, MloAdapter.mlo_item_to_resource_arn, filter_selected=True
        )
