from __future__ import annotations

import logging
from logging import Logger


class CliLogger(Logger):
    def __init__(self, name: str, level: int = logging.NOTSET) -> None:
        super().__init__(name, level)
