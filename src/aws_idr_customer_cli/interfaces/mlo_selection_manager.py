from abc import ABC, abstractmethod
from typing import List

from aws_idr_customer_cli.core.interactive.ui import InteractiveUI
from aws_idr_customer_cli.models.mlo_selection_manager import MloItem, MloResponseType


class BaseSelectionManager(ABC):
    """MLO (Multi Level Output) selection manager base class"""

    def __init__(self, items: List[MloItem]):
        self.items: List[MloItem] = items
        self.ui: InteractiveUI = InteractiveUI()

    @abstractmethod
    def _select_all_items(self, item_list: List[MloItem]) -> None:
        """Update 'selected' attribute for all items in the list
        Returns
            None as it manages selection in self.items
        """
        pass

    @abstractmethod
    def _manage_per_category_selection(self) -> None:
        """2nd level selection interface
        Returns
            None as it manages selection in self.items
        """
        pass

    @abstractmethod
    def _manage_all_categories(self) -> None:
        """3rd level selection interface
        Returns
            None as it manages selection in self.items
        """
        pass

    @abstractmethod
    def manage_selection(
        self, group_attribute_name: str, main_message_header: str
    ) -> MloResponseType:
        """Main selection interface

        Args:
            group_attribute_name: Display name for the attribute that we use to group items
                by (MloItem.group)
            main_message_header: The header message that will show at the top of the user prompt
                Example: Discovered the following resources:

        Returns:
            List of MloItems updated with the user selection (MloItem.selected)
        """
        pass
