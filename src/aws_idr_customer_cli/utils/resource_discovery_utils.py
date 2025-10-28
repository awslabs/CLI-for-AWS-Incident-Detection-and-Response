import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Union, cast

from dataclasses_json import DataClassJsonMixin, dataclass_json

from aws_idr_customer_cli.core.interactive.ui import InteractiveUI
from aws_idr_customer_cli.input.input_resource_discovery import InputResourceDiscovery
from aws_idr_customer_cli.models.alarm_models import AlarmRecommendation
from aws_idr_customer_cli.services.file_cache.data import ResourceArn
from aws_idr_customer_cli.utils.constants import DEFAULT_REGION, ItemType
from aws_idr_customer_cli.utils.mlo import MloSelectionManager
from aws_idr_customer_cli.utils.mlo_adapter import MloAdapter
from aws_idr_customer_cli.utils.session.interactive_session import (
    ACTION_BACK,
    ACTION_KEY,
    ACTION_RETRY,
)
from aws_idr_customer_cli.utils.validation.validator import (
    Validate,
    validate_alarm_arns,
)

# Constants for manual alarm ARN collection
BACK_COMMAND = "back"
FILE_INPUT_OPTION = "Upload a text file (recommended)"
MANUAL_INPUT_OPTION = "Enter ARNs manually"
GO_BACK_OPTION = "← Go back"
FILE_PATH_PROMPT = "Enter file path containing alarm ARNs (or 'back' to go back)"
MANUAL_ARNS_PROMPT = "Enter alarm ARNs (comma-separated)"

# Constants for alarm selection
ALARM_SELECTION_DEFAULT = "all"


@dataclass_json
@dataclass
class WorkloadDiscoveryData(DataClassJsonMixin):
    """Workload data for resource discovery operations."""

    regions: List[str]


@dataclass_json
@dataclass
class ResourceDiscoveryRequest(DataClassJsonMixin):
    """Request structure for resource discovery service."""

    workload: WorkloadDiscoveryData


def discover_resources_by_tags(
    input_resource_discovery: InputResourceDiscovery, regions: List[str]
) -> Union[Dict[str, str], Tuple[List[ResourceArn], List[Dict[str, Any]]]]:
    """Discover resources by tags and return the resource ARNs and tag filters used.

    Args:
        input_resource_discovery: The resource discovery service
        regions: List of AWS regions to discover resources in

    Returns:
        Either a navigation action dict or a tuple of (ResourceArn objects, tag filters used)
    """
    discovery_request = ResourceDiscoveryRequest(
        workload=WorkloadDiscoveryData(regions=regions)
    )

    result = input_resource_discovery.discover_by_tags(
        session_data=discovery_request.to_dict()
    )

    # Handle navigation action
    if isinstance(result, dict) and result.get("action") == "back":
        return {"action": "back"}

    # Extract resources and tags from tuple result
    resources, tag_filters = result

    # Extract ResourceArn objects from discovered resources
    resource_arns = []
    for resource in resources:
        if isinstance(resource, dict) and "ResourceArn" in resource:
            resource_arn = resource["ResourceArn"]
            if isinstance(resource_arn, ResourceArn):
                resource_arns.append(resource_arn)

    return (resource_arns, tag_filters)


def select_resources(
    ui: InteractiveUI,
    resource_arns: List[ResourceArn],
    group_attribute_name: str = "service",
    message_header: str = "Resource Selection",
    main_message: str = "Review and confirm the resources",
    item_attribute_name: str = "resource",
    continue_with_none: bool = False,
) -> Union[Dict[str, str], List[ResourceArn]]:
    """Select resources using MLOAdapter.

    Args:
        ui: User interface for displaying messages and prompts
        resource_arns: List of resource ARNs to select from
        group_attribute_name: Attribute name to group resources by
        message_header: Header message for selection UI
        main_message: Main message for selection UI
        continue_with_none: Whether to continue if no resources are selected

    Returns:
        Either a navigation action dict or a list of selected ResourceArn objects
    """
    if not resource_arns:
        ui.display_warning("No valid resources found for selection.")
        return []

    mlo_items = MloAdapter.resource_arns_to_mlo_items(resource_arns=resource_arns)
    if not mlo_items:
        ui.display_warning("Failed to prepare resources for selection.")
        return []

    mlo_manager = MloSelectionManager(items=mlo_items)
    mlo_response = mlo_manager.manage_selection(
        group_attribute_name=group_attribute_name,
        item_attribute_name=item_attribute_name,
        message_header=message_header,
        main_message=main_message,
    )

    if mlo_response.return_back:
        return {ACTION_KEY: ACTION_BACK}

    selected_resource_arns: List[ResourceArn] = MloAdapter.mlo_items_to_resource_arns(
        mlo_items=mlo_response.selected_items
    )

    selected_count = len(selected_resource_arns)
    item_name = (
        ItemType.RESOURCE.value
        if selected_count <= 1
        else f"{ItemType.RESOURCE.value}s"
    )
    ui.display_info(f"✅ Selection complete: {selected_count} {item_name} selected")

    if selected_count == 0 and not continue_with_none:
        proceed = ui.prompt_confirm(
            "No resources selected. Do you want to continue anyway?", False
        )
        if not proceed:
            return {ACTION_KEY: ACTION_RETRY}

    return selected_resource_arns


def select_alarms(
    ui: InteractiveUI,
    alarm_recommendations: List[AlarmRecommendation],
    message_header: str = "Alarm Creation Selection",
    main_message: str = "Review and confirm alarm recommendations",
    continue_with_none: bool = False,
) -> Union[Dict[str, str], List[AlarmRecommendation]]:
    """Select alarms using MLO with enhanced details for alarm-specific display.

    Args:
        ui: User interface for displaying messages and prompts
        alarm_recommendations: List of alarm recommendation objects to select from
        message_header: Header message for selection UI
        main_message: Main message for selection UI
        continue_with_none: Whether to continue if no alarms are selected

    Returns:
        Either a navigation action dict or
        a list of all AlarmRecommendation objects with selection state updated
    """
    if not alarm_recommendations:
        ui.display_warning("No alarm recommendations found for selection.")
        return []

    mlo_items = MloAdapter.alarm_recommendations_to_mlo_items(
        alarm_recommendations=alarm_recommendations
    )
    if not mlo_items:
        ui.display_warning("Failed to prepare alarm recommendations for selection.")
        return []

    mlo_manager = MloSelectionManager(items=mlo_items)
    # manage_selection returns ALL items with selection state updated
    mlo_response = mlo_manager.manage_selection(
        group_attribute_name="service",
        item_attribute_name="alarm",
        message_header=message_header,
        main_message=main_message,
    )

    if mlo_response.return_back:
        return {ACTION_KEY: ACTION_BACK}

    all_alarm_recommendations: List[AlarmRecommendation] = (
        MloAdapter.mlo_items_to_alarm_recommendations(
            mlo_items=mlo_response.selected_items
        )
    )

    selected_count = len([a for a in all_alarm_recommendations if a.is_selected])
    item_name = (
        ItemType.ALARM.value if selected_count <= 1 else f"{ItemType.ALARM.value}s"
    )
    ui.display_info(
        f"✅ Alarm selection complete: {selected_count} {item_name} selected"
    )

    if selected_count == 0 and not continue_with_none:
        proceed = ui.prompt_confirm(
            "No alarms selected. Do you want to continue anyway?", False
        )
        if not proceed:
            return {ACTION_KEY: ACTION_RETRY}

    return all_alarm_recommendations


def display_selected_resources(
    ui: InteractiveUI,
    resource_list: List[ResourceArn],
    title: str = "Selected resources for onboarding",
) -> None:
    """Display selected resources grouped by service type.

    Args:
        ui: User interface for displaying messages
        resource_list: List of ResourceArn objects to display
        title: Title to display above the resource list
    """
    if not resource_list:
        ui.display_warning("No resources selected for onboarding")
        return

    grouped_resources: Dict[str, List[ResourceArn]] = {}
    for resource in resource_list:
        service_type = resource.type
        if service_type not in grouped_resources:
            grouped_resources[service_type] = []
        grouped_resources[service_type].append(resource)

    total_count = len(resource_list)
    ui.display_info(f"📦 {title} ({total_count} total)")

    for service_type, resources in sorted(grouped_resources.items()):
        ui.display_info(f"\n🔗 {service_type} ({len(resources)} resources)")
        for resource in resources:
            resource_id = MloAdapter._create_friendly_resource_name(resource.arn)
            if resource.name and resource.name != resource_id:
                # Show both name and resource ID when Name tag is different
                display_name = f"{resource.name} ({resource_id})"
            else:
                # Show only resource ID when no Name tag
                display_name = resource_id
            ui.display_info(f"   • {display_name} ({resource.region})")


def collect_manual_alarm_arns(
    ui: InteractiveUI, validator: Validate, input_method: str
) -> Union[Dict[str, str], List[str]]:
    """Collect alarm ARNs via file or manual input."""
    if input_method == "file":
        return _collect_arns_from_file(ui, validator)
    else:
        return _collect_arns_manually(ui, validator)


def _collect_arns_from_file(
    ui: InteractiveUI, validator: Validate
) -> Union[Dict[str, str], List[str]]:
    """Collect alarm ARNs from file input."""
    ui.display_info("📁 Create a text file with one alarm ARN per line:")
    ui.display_info("  arn:aws:cloudwatch:us-east-1:123456789012:alarm:MyAlarm1")
    ui.display_info("  arn:aws:cloudwatch:us-east-1:123456789012:alarm:MyAlarm2")
    ui.display_info("")
    ui.display_info("💡 Generate from AWS CLI:")
    ui.display_info(
        "  aws cloudwatch describe-alarms --query 'MetricAlarms[].AlarmArn' --output text | tr '\\t' '\\n' > alarms.txt"  # noqa: E501
    )

    while True:
        file_path = ui.prompt_input(FILE_PATH_PROMPT)
        if not file_path or not file_path.strip():
            continue

        if file_path.strip().lower() == BACK_COMMAND:
            return {ACTION_KEY: ACTION_BACK}

        try:
            with open(file_path.strip(), "r", encoding="utf-8") as f:
                content = f.read()

            alarm_arns = [
                arn.strip() for arn in re.split(r"\r\n|\r|\n", content) if arn.strip()
            ]

            if not alarm_arns:
                ui.display_error("No alarm ARNs found in file")
                continue

            validated_arns = validate_alarm_arns(validator, alarm_arns)

            ui.display_info(
                f"✅ Successfully loaded {len(validated_arns)} alarm ARN(s)"
            )
            for i, arn in enumerate(validated_arns, 1):
                ui.display_info(f"  {i}. {arn}")

            return cast(List[str], validated_arns)

        except FileNotFoundError:
            ui.display_error(f"File not found: {file_path}")
            retry = ui.prompt_confirm("Try a different file?", True)
            if not retry:
                return {ACTION_KEY: ACTION_BACK}

        except PermissionError:
            ui.display_error(f"Permission denied reading file: {file_path}")
            retry = ui.prompt_confirm("Try a different file?", True)
            if not retry:
                return {ACTION_KEY: ACTION_BACK}

        except Exception as e:
            ui.display_error(f"Error reading file: {str(e)}")
            retry = ui.prompt_confirm("Try again?", True)
            if not retry:
                return {ACTION_KEY: ACTION_BACK}


def _collect_arns_manually(
    ui: InteractiveUI, validator: Validate
) -> Union[Dict[str, str], List[str]]:
    """Collect alarm ARNs from manual input."""
    ui.display_info("📝 Enter CloudWatch alarm ARNs separated by commas")
    ui.display_info(
        "Example: arn:aws:cloudwatch:us-east-1:123456789012:alarm:MyAlarm1,"
        "arn:aws:cloudwatch:us-east-1:123456789012:alarm:MyAlarm2"
    )
    ui.display_info("Type 'back' to go back to input method selection")

    try:
        input_text = ui.prompt_input(MANUAL_ARNS_PROMPT)

        if input_text.strip().lower() == BACK_COMMAND:
            return {ACTION_KEY: ACTION_BACK}

        if not input_text.strip():
            ui.display_warning("No alarm ARNs provided")
            return {ACTION_KEY: ACTION_RETRY}

        alarm_arns = [arn.strip() for arn in input_text.split(",") if arn.strip()]

        if not alarm_arns:
            ui.display_warning("No valid alarm ARNs found")
            return {ACTION_KEY: ACTION_RETRY}

        validated_arns = validate_alarm_arns(validator, alarm_arns)

        ui.display_info(f"✅ Collected {len(validated_arns)} alarm ARN(s)")
        for i, arn in enumerate(validated_arns, 1):
            ui.display_info(f"  {i}. {arn}")

        return cast(List[str], validated_arns)

    except Exception as e:
        ui.display_error(f"Error validating ARNs: {str(e)}")
        return {ACTION_KEY: ACTION_RETRY}


def _group_alarms_by_region(alarm_arns: List[str]) -> Dict[str, List[str]]:
    """Group alarm ARNs by region."""
    alarms_by_region: Dict[str, List[str]] = {}
    for arn in alarm_arns:
        region = arn.split(":")[3] if ":" in arn else DEFAULT_REGION
        if region not in alarms_by_region:
            alarms_by_region[region] = []
        alarms_by_region[region].append(arn)
    return alarms_by_region


def _display_alarms_by_region(
    ui: InteractiveUI, alarms_by_region: Dict[str, List[str]]
) -> None:
    """Display alarms grouped by region."""
    counter = 1
    for region in sorted(alarms_by_region.keys()):
        ui.display_info(f"{region}")
        for arn in alarms_by_region[region]:
            alarm_name = arn.split(":")[-1]
            ui.display_info(f"  {counter:2d}  {alarm_name}")
            counter += 1
        ui.display_info("")


def _display_selection_options(ui: InteractiveUI) -> None:
    """Display alarm selection options."""
    ui.console.print("Select alarms:")
    options = [
        "all - select all alarms",
        "Numbers/ranges: 1,3 or 1-3 or 1,3-5",
        "Region name to select all in that region (e.g., us-west-2)",
        "back - return to previous step",
    ]
    for option in options:
        ui.console.print(f"  • {option}")


def _parse_numeric_selection(selection: str) -> set[int]:
    """Parse numeric selection like '1,3-5,7' into set of indices."""
    selected_indices: set[int] = set()
    for part in selection.split(","):
        part = part.strip()
        if "-" in part:
            start, end = map(int, part.split("-"))
            selected_indices.update(range(start, end + 1))
        else:
            selected_indices.add(int(part))
    return selected_indices


def select_cloudwatch_alarms(
    ui: InteractiveUI, alarm_arns: List[str]
) -> Union[Dict[str, str], List[str]]:
    """Select CloudWatch alarms with region-grouped display."""
    if not alarm_arns:
        return []

    alarms_by_region = _group_alarms_by_region(alarm_arns)
    total = len(alarm_arns)

    ui.display_info(f"{total} alarm(s) found:\n")
    _display_alarms_by_region(ui, alarms_by_region)
    _display_selection_options(ui)

    while True:
        try:
            selection = (
                ui.prompt_input(message="Selection", default=ALARM_SELECTION_DEFAULT)
                .strip()
                .lower()
            )

            if selection == "back":
                return {ACTION_KEY: ACTION_BACK}

            if selection == "all":
                return alarm_arns

            # Check if it's a region name
            if selection in alarms_by_region:
                selected = alarms_by_region[selection]
                ui.display_info(
                    f"\n✅ Selected {len(selected)} alarm(s) from {selection}"
                )
                return selected

            # Parse numeric selection
            selected_indices = _parse_numeric_selection(selection)

            # Validate
            invalid = [i for i in selected_indices if i < 1 or i > total]
            if invalid:
                ui.display_error(f"Invalid: {invalid}. Use 1-{total}")
                continue

            if not selected_indices:
                ui.display_error("Select at least one alarm")
                continue

            selected_arns = [alarm_arns[i - 1] for i in sorted(selected_indices)]
            ui.display_info(f"\n✅ Selected {len(selected_arns)} alarm(s)")
            return selected_arns

        except ValueError:
            ui.display_error("Invalid format. Use: 1,3 or 1-3 or region name")
        except Exception as e:
            ui.display_error(f"Error: {str(e)}")
