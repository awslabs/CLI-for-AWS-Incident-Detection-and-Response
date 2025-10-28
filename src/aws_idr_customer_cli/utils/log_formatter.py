import logging
from logging import LogRecord

import colorama
from colorama import Fore, Style

colorama.init()


class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds colors to log messages based on their level."""

    COLORS = {
        "DEBUG": Fore.BLUE,
        "INFO": Fore.GREEN,
        "WARNING": Fore.YELLOW,
        "ERROR": Fore.RED,
        "CRITICAL": Fore.RED + Style.BRIGHT,
    }

    def format(self, record: LogRecord) -> str:
        message = super().format(record)

        if record.levelname in self.COLORS:
            color = self.COLORS[record.levelname]
            parts = message.split("]", 1)
            if len(parts) > 1:
                level_end = parts[0].rfind("[") + len("[")
                colored_level = (
                    parts[0][:level_end]
                    + color
                    + parts[0][level_end:]
                    + Style.RESET_ALL
                )
                return colored_level + "]" + color + parts[1] + Style.RESET_ALL
            return color + message + Style.RESET_ALL

        return message
