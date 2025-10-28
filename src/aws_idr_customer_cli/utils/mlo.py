from collections import Counter
from typing import Dict, List, Optional, cast

from injector import inject

from aws_idr_customer_cli.core.interactive.ui import InteractiveUI
from aws_idr_customer_cli.interfaces.mlo_selection_manager import (
    BaseSelectionManager,
)
from aws_idr_customer_cli.models.mlo_selection_manager import MloItem, MloResponseType
from aws_idr_customer_cli.utils.session.interactive_session import STYLE_DIM


class MloSelectionManager(BaseSelectionManager):
    """
    Generic MLO (Multi Level Output) selection manager.

    Primary use cases:
    1. Manage resource selection for resource discovery.
    2. Manage alarm selection for alarm creation.

    It takes a standardized item list as an input and manages customer
    friendly presentation and selection.

    Usage example:

    mlo = MloSelectionManager(items=mlo_items)
    selected_items = mlo.manage_selection(
            group_attribute_name="type",
            message_header="Resource discovery",
            main_message=(f"Discovered {len(resources)} resources total.\n"
                "Review and confirm resource selection."),
        )
    """

    ALL_REGIONS = "All regions"

    @inject
    def __init__(self, items: List[MloItem]) -> None:
        super().__init__(items=items)
        self.ui: InteractiveUI = InteractiveUI()
        # regional attributes
        self.selected_region: Optional[str] = None
        self.region_list: Optional[List[str]] = None
        self.region_to_item_dict: Optional[Dict[str, List[MloItem]]] = None
        self.item_attribute_name: str = "item"
        self.group_attribute_name: str = "group"
        self.message_header: str = ""
        self.main_message: str = ""
        self.breadcrumbs: List[str] = []
        self.return_back_in_cli: bool = (
            False  # Flag to allow users to go to the pervious CLI step
        )

    def manage_selection(
        self,
        group_attribute_name: str,
        message_header: str,
        main_message: str,
        item_attribute_name: str,
    ) -> MloResponseType:
        self.group_attribute_name = group_attribute_name
        self.item_attribute_name = item_attribute_name
        self.message_header = message_header
        self.main_message = main_message

        self._manage_initial_selection()

        confirmed_exit = False
        while not confirmed_exit and not self.return_back_in_cli:
            confirmed_exit = self._display_summary_and_confirm_exit()

        response = MloResponseType(
            selected_items=cast(List[MloItem], self.items),
            return_back=self.return_back_in_cli,
        )
        return response

    def _manage_initial_selection(self) -> None:
        self._populate_regional_attributes()

        resource_count = len(self.items)
        region_count = len(self.region_list or [])
        if self.region_list and "global" in self.region_list:
            region_count -= 1

        self.ui.display_header(self.message_header)

        self.breadcrumbs.append(f"Total {self.item_attribute_name} view")
        self._display_breadcrumbs()

        message = (
            f"Discovered {resource_count} eligible {self.item_attribute_name}s "
            f"in {region_count} regions."
        )
        self.ui.display_info(message=message, style="white")

        note_message = (
            "NOTE: Resources not eligible for monitoring like IAM roles, security \n"
            "groups, and subnets are excluded."
        )
        self.ui.display_info(message=note_message, style=STYLE_DIM)

        option_one_suffix = ""
        if self.item_attribute_name == "resource":
            option_one_suffix = " your workload onboarding information"

        options = [
            f"1 → Select all {resource_count} {self.item_attribute_name}s in "
            f"{region_count} regions and proceed to submitting{option_one_suffix}",
            f"2 → Review and customize {self.item_attribute_name} selection",
        ]

        if self.item_attribute_name == "resource":
            options.append("3 → Go back to change the tag filter")

        choice = self.ui.select_option(
            options=options,
            message="What would you like to do?",
            explicit_index=True,
            max_choice_number=len(options),
        )

        self.breadcrumbs.pop()

        if choice == 0:  # Select all and finish
            self._select_all_items(item_list=self.items)
        elif choice == 1:  # Review and customize
            self._manage_region_selection()
        elif choice == 2:  # Go back to change the tag filter
            self.return_back_in_cli = True

    def _manage_region_selection(self) -> None:
        if not self.region_list or not self.region_to_item_dict:
            raise ValueError("Region list is not populated. Cannot proceed.")

        while True:
            self.ui.display_header(self.message_header)

            self.breadcrumbs.append("Regional view")
            self._display_breadcrumbs()

            message = f"You've chosen to review and customize {self.item_attribute_name} selection."
            self.ui.display_info(message=message, style="white")

            option_one_suffix = ""
            if self.item_attribute_name == "resource":
                option_one_suffix = " your workload onboarding information"

            selected_per_region_count = self._count_selected_items_per_region(
                items=self.items
            )
            total_selected = self._total_selected_count(items=self.items)
            total_resources = len(self.items)
            region_count = len(self.region_list or [])
            if self.region_list and "global" in self.region_list:
                region_count -= 1

            # Separate global and regional resources
            global_count = selected_per_region_count.get("global", 0)
            global_total = len(self.region_to_item_dict.get("global", []))

            options = [
                f"1 → Select all {total_resources} {self.item_attribute_name}s in "
                f"{region_count} regions and proceed to submitting{option_one_suffix}",
                f"2 → Deselect all {total_resources} {self.item_attribute_name}s",
            ]
            next_option = 3

            accept_current_option: Optional[int] = None
            if total_selected > 0:
                accept_current_option = next_option - 1
                options.append(
                    f"3 → Accept current selection (Currently {total_selected} selected "
                    f"of {total_resources}) and proceed to onboarding"
                )
                next_option += 1

            review_in_all_option = next_option - 1
            options.append(
                f"{next_option} → Review {self.item_attribute_name}s in all "
                f"({region_count}) regions and customize selection (Currently "
                f"{total_selected} selected of {total_resources})"
            )
            next_option += 1

            # Add global resources option if they exist
            global_option: Optional[int] = None
            if "global" in self.region_to_item_dict:
                global_option = next_option - 1
                options.append(
                    f"{next_option} → Review global {self.item_attribute_name}s "
                    f"(Currently {global_count} selected of {global_total})"
                )
                next_option += 1

            # Add regional options
            region_start_option = next_option - 1
            for region in self.region_list or []:
                if region != "global":
                    selected_count = selected_per_region_count.get(region, 0)
                    total_count = len(self.region_to_item_dict[region])
                    options.append(
                        f"{next_option} → Review {region} {self.item_attribute_name}s "
                        f"(Currently {selected_count} of {total_count} selected)"
                    )
                    next_option += 1

            go_back_option = next_option - 1
            if self.item_attribute_name == "resource":
                options.append(f"{next_option} → Go back to change the tag filter")

            choice = self.ui.select_option(
                options=options,
                message="What would you like to do?",
                explicit_index=True,
                max_choice_number=len(options),
            )

            if choice == 0:  # Select all
                self._select_all_items(item_list=self.items)
                self.breadcrumbs.pop()
                break
            elif choice == 1:  # Deselect all
                self._deselect_all_items(item_list=self.items)
            elif (
                accept_current_option and choice == accept_current_option
            ):  # Accept current selection
                self.breadcrumbs.pop()
                break
            elif choice == review_in_all_option:  # Review all regions
                self.selected_region = "All"
                self._manage_per_category_selection(items=self.items)
            elif global_option and choice == global_option:  # Review global
                self.selected_region = "global"
                self._manage_per_category_selection(
                    items=self.region_to_item_dict["global"]
                )
            elif choice >= region_start_option and choice < go_back_option:
                # Review specific region
                base_offset = 5 if total_selected > 0 else 4
                if "global" not in self.region_to_item_dict:
                    base_offset -= 1
                region_index = choice - base_offset
                non_global_regions = [r for r in self.region_list if r != "global"]
                if region_index < len(non_global_regions):
                    self.selected_region = non_global_regions[region_index]
                    self._manage_per_category_selection(
                        items=self.region_to_item_dict[self.selected_region]
                    )
            elif choice == go_back_option:
                self.return_back_in_cli = True
                self.breadcrumbs.pop()
                break

            self.breadcrumbs.pop()

    def _manage_per_category_selection(self, items: List[MloItem]) -> None:

        while True:
            self.ui.display_header(self.message_header)

            self.breadcrumbs.append(
                f"{self.item_attribute_name.capitalize()} group view in "
                f"{self.selected_region} region"
            )
            self._display_breadcrumbs()

            self.ui.display_info(
                message="To change region, use 'Accept and go back' option",
                style=STYLE_DIM,
            )

            # Display resource count per type
            item_group_detail_dict = self._get_per_group_summary(items=items)
            total_selected_count = self._total_selected_count(items=items)
            total_resources = len(items)

            group_detail_list: List[str] = []
            for group_detail in item_group_detail_dict.values():
                group_detail_list.append(f"{group_detail}\n")

            highlight = "[yellow]" if total_selected_count > 0 else ""
            end_hl = "[/yellow]" if total_selected_count > 0 else ""

            resource_summary = (
                f"{self.item_attribute_name.capitalize()} count per type in "
                f"{self.selected_region} region:\n"
                f"{''.join(group_detail_list)}"
                f"Currently selected: {highlight}{total_selected_count}{end_hl} of "
                f"{total_resources} {self.item_attribute_name}s"
            )

            self.ui.display_info(message=resource_summary, style="white")

            if len(self.breadcrumbs) > 1:
                previous_bc = self.breadcrumbs[-2]
            else:
                previous_bc = "Regional view"

            options = [
                f"1 → Select all {total_resources} {self.item_attribute_name}s and "
                f'go back to "Regional view"',
                f"2 → Deselect all {total_resources} {self.item_attribute_name}s",
                "3 → Accept current resource selection "
                f"({total_selected_count} of {total_resources} "
                f'{self.item_attribute_name}s selected) and go back to "{previous_bc}"',
                f"4 → Review individual {self.item_attribute_name}s and "
                f"customize selection",
            ]

            choice = self.ui.select_option(
                options=options,
                message="What would you like to do?",
                explicit_index=True,
                max_choice_number=len(options),
            )

            if choice == 0:  # Select all
                self._select_all_items(item_list=items)
                self.breadcrumbs.pop()
                break
            elif choice == 1:  # Deselect all
                self._deselect_all_items(item_list=items)
            elif choice == 2:  # Accept current selection
                self.breadcrumbs.pop()
                break
            elif choice == 3:  # Review individual resources
                self._manage_detailed_item_selection(items=items)

            self.breadcrumbs.pop()

    def _manage_detailed_item_selection(self, items: List[MloItem]) -> None:

        while True:
            self.ui.display_header(self.message_header)

            self.breadcrumbs.append(
                f"Individual {self.item_attribute_name} view in "
                f"{self.selected_region} region"
            )
            self._display_breadcrumbs()

            item_count = len(items)

            # Calculate action choice numbers
            deselect_all_choice = item_count
            go_back_choice = deselect_all_choice + 1
            max_choice = go_back_choice + 1

            # Build item details display
            per_item_detailed_string_list = []
            for i, item in enumerate(items, 1):  # Start from 1 for display
                item_friendly_name = item.friendly_name or ""
                selected = (
                    "[yellow]selected[/yellow]" if item.selected else "not selected"
                )
                per_item_detailed_string_list.append(
                    f"{i}: {item.group}: {item_friendly_name} - {selected}\n"
                )
                if item.details:
                    per_item_detailed_string_list.append(f"    {item.details}\n")

            self.ui.display_info(
                message="To change region, use 'Accept and go back' option",
                style=STYLE_DIM,
            )

            total_selected_count = self._total_selected_count(items=items)

            level_three_message = (
                f"{self.item_attribute_name.capitalize()} list in "
                f"{self.selected_region} region:\n"
                "Item details:\n"
                f"{''.join(per_item_detailed_string_list)}"
                f"Currently selected: {total_selected_count} "
                f"of {len(items)} items\n"
            )

            self.ui.display_info(message=level_three_message, style="white")

            if len(self.breadcrumbs) > 1:
                previous_bc = self.breadcrumbs[-2]
            else:
                previous_bc = f"{self.item_attribute_name.capitalize()} group view"

            level_three_options = [
                f"1-{item_count} → Mark {self.item_attribute_name} as selected by number",
                f"{deselect_all_choice + 1} → Deselect all",
                f"{go_back_choice + 1} → Accept current {self.item_attribute_name} selection "
                f"({total_selected_count} selected of {len(items)}) and go back to "
                f'"{previous_bc}"',
            ]

            choice = self.ui.select_option(
                options=level_three_options,
                message="What would you like to do?",
                explicit_index=True,
                max_choice_number=max_choice,
            )

            if choice < item_count:
                items[choice].selected = True
            elif choice == deselect_all_choice:
                self._deselect_all_items(item_list=items)
            elif choice == go_back_choice:
                self.breadcrumbs.pop()
                break

            self.breadcrumbs.pop()

    def _manage_all_categories(self, items: List[MloItem]) -> None:
        self._manage_detailed_item_selection(items=items)

    @staticmethod
    def _get_group_selection_count(items: List[MloItem]) -> Dict[str, int]:
        # doing list cause it's faster for iterations than a set
        unique_group_list = list(set(item.group for item in items))
        return {
            group: sum(1 for i in items if i.group == group and i.selected)
            for group in unique_group_list
        }

    @staticmethod
    def _total_selected_count(items: List[MloItem]) -> int:
        return sum(1 for item in items if item.selected)

    def _get_per_group_summary(self, items: List[MloItem]) -> Dict[str, str]:
        group_counts: Dict[str, int] = Counter(item.group for item in items)
        per_group_selected_count: Dict[str, int] = self._get_group_selection_count(
            items=items
        )

        output_dict = {}
        for group, count in group_counts.items():

            selected_count = per_group_selected_count[group]
            color = "[yellow]" if selected_count > 0 else ""
            color_end = "[/yellow]" if selected_count > 0 else ""

            output_dict[group] = (
                f"  {group}: {count}, "
                f"{color}selected {per_group_selected_count[group]}{color_end}"
            )

        return output_dict

    @staticmethod
    def _deselect_all_items(item_list: List[MloItem]) -> None:
        for item in item_list:
            item.selected = False

    def _select_all_items(self, item_list: List[MloItem]) -> None:
        for item in item_list:
            item.selected = True

    def _get_items_for_a_group(self, items: List[MloItem], group: str) -> List[MloItem]:
        return [item for item in items if item.group == group]

    def _count_selected_items_per_region(self, items: List[MloItem]) -> Dict[str, int]:
        items_per_region_counter_dic = {}
        for item in items:
            if item.region not in items_per_region_counter_dic:
                items_per_region_counter_dic[item.region] = 1 if item.selected else 0
            else:
                if item.selected:
                    items_per_region_counter_dic[item.region] += 1
        return items_per_region_counter_dic

    def _populate_regional_attributes(self) -> None:
        self.region_to_item_dict = {}
        self.region_list = []

        for item in self.items:
            if item.region not in self.region_to_item_dict:
                self.region_to_item_dict[item.region] = [item]
            else:
                self.region_to_item_dict[item.region].append(item)
            if item.region not in self.region_list:
                self.region_list.append(item.region)

    def _display_breadcrumbs(self) -> None:
        breadcrumbs_text = " [yellow]>[/yellow] ".join(self.breadcrumbs)
        line = "─" * len(breadcrumbs_text)
        self.ui.display_info(message=line, style="yellow")
        self.ui.display_info(message=breadcrumbs_text, style="white")
        self.ui.display_info(message=line, style="yellow")

    def _display_summary_and_confirm_exit(self) -> bool:
        if not self.region_list or not self.region_to_item_dict:
            raise ValueError("Region list is not populated. Cannot proceed.")

        self.breadcrumbs.append("Final confirmation")
        self._display_breadcrumbs()

        selected_per_region = self._count_selected_items_per_region(items=self.items)
        total_selected = self._total_selected_count(items=self.items)
        total_items = len(self.items)

        # Build region lines and find longest
        region_lines = []
        for region in sorted(selected_per_region.keys()):
            region_items = self.region_to_item_dict.get(region, [])
            selected_count = selected_per_region[region]
            total_count = len(region_items)
            region_lines.append(f"{region}: {selected_count} selected of {total_count}")

        max_line_length = max(len(line) for line in region_lines)

        self.ui.display_info(message="Selection summary", style="white")
        self.ui.display_info(message="─" * max_line_length, style="yellow")

        for line in region_lines:
            self.ui.display_info(message=line, style="white")

        self.ui.display_info(message="─" * max_line_length, style="yellow")
        self.ui.display_info(
            message=f"TOTAL: {total_selected} selected of {total_items}", style="white"
        )

        options = [
            f"1 → Confirm and continue with {total_selected} of {total_items} selected",
            "2 → Edit selection",
        ]

        choice = self.ui.select_option(
            options=options,
            message="What would you like to do?",
            explicit_index=True,
            max_choice_number=2,
        )

        self.breadcrumbs.pop()

        if choice == 0:  # Confirm and continue
            return True
        else:  # Edit selection
            self._manage_region_selection()
            return False
