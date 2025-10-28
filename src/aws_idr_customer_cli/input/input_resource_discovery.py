from typing import Any, Dict, List, Tuple, Union, cast

from injector import inject

from aws_idr_customer_cli.core.interactive.ui import InteractiveUI
from aws_idr_customer_cli.exceptions import ValidationError
from aws_idr_customer_cli.services.input_module.resource_finder_service import (
    ResourceFinderService,
)
from aws_idr_customer_cli.utils.session.interactive_session import (
    ACTION_BACK,
    ACTION_KEY,
    ACTION_RETRY,
    STYLE_BLUE,
    STYLE_DIM,
)
from aws_idr_customer_cli.utils.validation.aws_validation_context import aws_validation
from aws_idr_customer_cli.utils.validation.validator import Validate

WORKLOAD_KEY = "workload"
WORKLOAD_REGIONS = "regions"
CLOUDWATCH_ALARM_RESOURCE_TYPE = "cloudwatch:alarm"


class InputResourceDiscovery:
    """
    Common Input handler.
    RGTA implementation only for Beta
    """

    @inject
    def __init__(
        self,
        ui: InteractiveUI,
        resource_finder_service: ResourceFinderService,
        validator: Validate,
    ) -> None:
        self.ui = ui
        self.resource_finder_service = resource_finder_service
        self.validator = validator

    def discover_by_tags(
        self, session_data: Dict[str, Any]
    ) -> Union[Tuple[List[Dict[str, Any]], List[Dict[str, Any]]], Dict[str, str]]:
        """
        Handle complete tag-based resource discovery workflow with RGTA.

        Returns:
            Tuple of (discovered resources, tag filters used) or navigation action dict
        """
        try:
            regions = self._extract_regions_from_session(session_data)
            return self._execute_tag_discovery(regions=regions)
        except ValidationError as e:
            self.ui.display_error(f"Tag validation failed: {e.message}")
            return [], []

    def discover_alarms_by_tags(
        self, regions: List[str]
    ) -> Union[None, dict[str, str], tuple[list[Any], list[dict[str, Any]]]]:
        """Discover CloudWatch alarms by tags - simplified workflow for alarm ingestion."""

        while True:
            input_method = self._get_tag_input_method()
            if input_method is None:
                return {ACTION_KEY: ACTION_BACK}

            # Get tag filters and confirm
            tag_filters, tag_display = self._get_tag_filters(input_method=input_method)
            if tag_filters is None or not self._confirm_search(tag_display=tag_display):
                continue

            # Search for alarms
            self.ui.display_info(
                "🔍 Searching for CloudWatch alarms...", style=STYLE_BLUE
            )

            resources = self.resource_finder_service.find_resources_by_tags(
                tags=tag_filters,
                regions=regions,
                resource_types=[CLOUDWATCH_ALARM_RESOURCE_TYPE],
                resource_label="CloudWatch alarms",
            )

            if not resources:
                action = self._handle_no_results()
                if action == ACTION_RETRY:
                    continue
                elif action == ACTION_BACK:
                    return {ACTION_KEY: ACTION_BACK}
                else:  # "continue"
                    return [], tag_filters

            # Extract ARN strings
            alarm_arns = [r["ResourceArn"].arn for r in resources if "ResourceArn" in r]

            return alarm_arns, tag_filters

    def _extract_regions_from_session(self, session_data: Dict[str, Any]) -> List[str]:
        """Extract regions from session data."""
        workload_data = session_data.get(WORKLOAD_KEY, {})
        regions: List[str] = workload_data.get(WORKLOAD_REGIONS, [])

        if not regions:
            raise ValidationError("No regions found in session data")

        return regions

    def _execute_tag_discovery(
        self, regions: List[str]
    ) -> Union[Tuple[List[Dict[str, Any]], List[Dict[str, Any]]], Dict[str, str]]:
        """Execute the complete tag discovery workflow."""
        while True:
            input_method = self._get_tag_input_method()
            if input_method is None:
                return {"action": "back"}

            # Get tag filters and confirm
            tag_filters, tag_display = self._get_tag_filters(input_method=input_method)
            if tag_filters is None or not self._confirm_search(tag_display=tag_display):
                continue

            resources = self._search_resources(
                tag_filters=tag_filters, tag_display=tag_display, regions=regions
            )
            if resources is None:
                continue

            # Handle empty results
            if not resources:
                action = self._handle_no_results()
                if action == "retry":
                    continue
                elif action == "back":
                    return {"action": "back"}
                else:  # "continue"
                    return ([], tag_filters)

            return (resources, tag_filters)

    def _get_tag_input_method(self) -> Union[int, None]:
        """Get user's preferred tag input method."""
        result = self.ui.select_option(
            [
                "Single tag (key and value separately)",
                "Multiple tags (key1=value1,key2=value1|value2)",
            ],
            "How would you like to specify tags?",
        )
        return cast(int, result)

    def _get_tag_filters(
        self, input_method: int
    ) -> tuple[Union[List[Dict[str, Any]], None], str]:
        """Get tag filters based on input method."""
        try:
            with aws_validation(self.ui, self.validator) as prompt:
                if input_method == 0:  # Single tag
                    tag_key = prompt.tag_key("Tag key", default="Application")
                    tag_value = prompt.tag_values("Tag value")
                    tag_filters = [{"Key": tag_key, "Values": tag_value}]
                    tag_display = f"{tag_key}={tag_value}"
                    return tag_filters, tag_display
                else:  # Multiple tags
                    tag_pairs = prompt.tag_filter_pairs(
                        "Enter tags to search for",
                        default="Environment=production|prod",
                    )
                    if not tag_pairs:
                        self.ui.display_error("No tags specified")
                        return None, ""

                    tag_filters = []
                    for tag in tag_pairs:
                        tag_filters.append(
                            {"Key": tag["Name"], "Values": tag["Values"]}
                        )

                    tag_display = ", ".join(
                        [f"{tag['Key']}={tag['Values']}" for tag in tag_filters]
                    )
                    return tag_filters, tag_display
        except ValidationError:
            return None, ""

    def _confirm_search(self, tag_display: str) -> bool:
        """Confirm search with user."""
        result = self.ui.prompt_confirm(
            f"Would you like to proceed with {tag_display}?", True
        )
        return cast(bool, result)

    def _search_resources(
        self, tag_filters: List[Dict[str, Any]], tag_display: str, regions: List[str]
    ) -> Union[List[Dict[str, Any]], None]:
        """Execute RGTA search and return results."""
        try:
            self.ui.display_info(
                message=f"🔍 Searching for resources with tags: {tag_display}",
                style=STYLE_BLUE,
            )

            resources = self.resource_finder_service.find_functional_resources_by_tags(
                tags=tag_filters, regions=regions
            )

            if resources:
                self._show_resource_summary(resources=resources)

            return cast(List[Dict[str, Any]], resources)

        except Exception as e:
            self.ui.display_error(f"Error during resource search: {str(e)}")
            return None

    def _handle_no_results(self) -> str:
        """Handle empty search results."""
        self.ui.display_warning(
            "No eligible resources found matching the specified tags"
        )

        choice = self.ui.select_option(
            [
                "Try different tags",
                "Continue with empty resource list",
                "← Go back to previous step",
            ],
            "What would you like to do?",
        )
        choice_int = cast(int, choice)

        if choice_int == 0:
            return "retry"
        elif choice_int == 1:
            return "continue"
        else:
            return "back"

    def _show_resource_summary(self, resources: List[Dict[str, Any]]) -> None:
        """Show summary of discovered resources."""
        if not resources:
            return

        # Group by service type
        by_service: Dict[str, int] = {}
        for resource in resources:
            resource_arn = resource.get("ResourceArn")
            if resource_arn:
                service_type = getattr(resource_arn, "type", "Unknown")
                by_service[service_type] = by_service.get(service_type, 0) + 1

        self.ui.display_info(message="📋 Resource Summary:", style=STYLE_DIM)
        for service, count in sorted(by_service.items()):
            self.ui.display_info(
                message=f"  • {service}: {count} resources", style=STYLE_DIM
            )
