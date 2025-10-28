from abc import ABC, abstractmethod
from typing import List, Optional


class InputService(ABC):
    """Interface for handling user input in the CLI application."""

    @abstractmethod
    def prompt_for_input(self, prompt_text: str, default: Optional[str] = None) -> str:
        """Prompt the user for text input with an optional default value.

        Args:
            prompt_text: The text to display when prompting
            default: Optional default value if user doesn't provide input

        Returns:
            The user's input as a string
        """
        pass

    @abstractmethod
    def prompt_for_confirmation(self, prompt_text: str, default: bool = True) -> bool:
        """Prompt the user for a yes/no confirmation.

        Args:
            prompt_text: The text to display when prompting
            default: Default value (True for yes, False for no)

        Returns:
            True if confirmed, False otherwise
        """
        pass

    @abstractmethod
    def prompt_for_choice(
        self, prompt_text: str, choices: List[str], default: Optional[int] = None
    ) -> str:
        """Prompt the user to select from a list of choices.

        Args:
            prompt_text: The text to display when prompting
            choices: List of choices to present to the user
            default: Optional default choice index

        Returns:
            The selected choice as a string
        """
        pass
