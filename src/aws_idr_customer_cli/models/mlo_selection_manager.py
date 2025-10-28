from dataclasses import dataclass
from typing import Any, List, Optional


@dataclass
# MLO (Multi Level Output) item model
class MloItem:
    id: str
    group: str
    region: str
    friendly_name: Optional[str] = None
    details: Optional[str] = None
    selected: bool = False
    source_data: Optional[Any] = None


@dataclass
class MloResponseType:
    selected_items: List[MloItem]
    return_back: bool
