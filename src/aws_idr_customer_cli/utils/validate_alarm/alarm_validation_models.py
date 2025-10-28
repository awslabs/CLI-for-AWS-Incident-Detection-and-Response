from dataclasses import dataclass
from typing import Dict


@dataclass
class ValidationFlags:
    """Validation flags for alarm assessment."""

    is_noisy: bool = False
    has_datapoints: bool = True
    is_infrastructure: bool = False
    is_unsuitable: bool = False
    is_non_prod: bool = False
    is_critical: bool = False
    is_alarming: bool = False
    insufficient_data: bool = False
    treat_missing_data_issue: bool = False
    is_cross_account: bool = False

    def to_dict(self) -> Dict[str, bool]:
        """Convert to dictionary."""
        return {
            "is_noisy": self.is_noisy,
            "has_datapoints": self.has_datapoints,
            "is_infrastructure": self.is_infrastructure,
            "is_unsuitable": self.is_unsuitable,
            "is_non_prod": self.is_non_prod,
            "is_critical": self.is_critical,
            "is_alarming": self.is_alarming,
            "insufficient_data": self.insufficient_data,
            "treat_missing_data_issue": self.treat_missing_data_issue,
            "is_cross_account": self.is_cross_account,
        }
