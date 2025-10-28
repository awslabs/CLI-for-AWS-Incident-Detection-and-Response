from typing import List, Optional, cast

import click

from aws_idr_customer_cli.interfaces.input_service import InputService
from aws_idr_customer_cli.utils.log_handlers import CliLogger


class ClickInputService(InputService):
    """Implementation of InputService using Click library."""

    def __init__(self, logger: CliLogger) -> None:
        """Initialize the input service.

        Args:
            logger: Logger for recording input operations
        """
        self.logger = logger

    def prompt_for_input(self, prompt_text: str, default: Optional[str] = None) -> str:
        """Prompt the user for text input with an optional default value.

        Args:
            prompt_text: The text to display when prompting
            default: Optional default value if user doesn't provide input

        Returns:
            The user's input as a string
        """
        self.logger.debug(f"Prompting for input: {prompt_text}")
        result = cast(
            str, click.prompt(prompt_text, default=default, show_default=True)
        )
        return result

    def prompt_for_confirmation(self, prompt_text: str, default: bool = True) -> bool:
        """Prompt the user for a yes/no confirmation.

        Args:
            prompt_text: The text to display when prompting
            default: Default value (True for yes, False for no)

        Returns:
            True if confirmed, False otherwise
        """
        self.logger.debug(f"Prompting for confirmation: {prompt_text}")
        return click.confirm(prompt_text, default=default)

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
        self.logger.debug(f"Prompting for choice: {prompt_text}")
        result = cast(
            str,
            click.prompt(
                prompt_text,
                type=click.Choice(choices),
                default=choices[default] if default is not None else None,
                show_choices=True,
            ),
        )
        return result
