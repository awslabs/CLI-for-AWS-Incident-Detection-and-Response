from enum import Enum
from typing import Dict, Optional

SUPPORT_CASE_KEY = "Support Case"


class Stage(Enum):
    """Feature stages."""

    DEV = "dev"
    BETA = "beta"
    GA = "ga"


class Feature(Enum):
    """Available features."""

    MVP = "mvp"


class FeatureFlags:
    """Simple feature flag manager."""

    # Feature flag configuration
    _FLAGS: Dict[Feature, Stage] = {
        Feature.MVP: Stage.GA,
    }
    # Configuration per feature per stage
    _FEATURE_CONFIGS = {
        Feature.MVP: {
            Stage.DEV: {
                SUPPORT_CASE_KEY: {
                    "severity": "low",
                    "category": "prophet-aria",
                    "issue_type": "technical",
                    "language": "en",
                    "service_code": "service-kumo-testing-technical",  # IDR recommended testing CTI
                }
            },
            Stage.BETA: {
                SUPPORT_CASE_KEY: {
                    "severity": "low",
                    "category": "onboard-new-workload",
                    "issue_type": "technical",
                    "language": "en",
                    "service_code": "service-incident-detection-and-response",
                }
            },
            Stage.GA: {
                SUPPORT_CASE_KEY: {
                    "severity": "low",
                    "category": "onboard-new-workload",
                    "issue_type": "technical",
                    "language": "en",
                    "service_code": "service-incident-detection-and-response",
                }
            },
        }
    }

    @classmethod
    def get_stage(cls, feature: Feature) -> Optional[Stage]:
        """Get the stage for a feature.
        Args:
            feature: The feature to check
        Returns:
            Stage of the feature, or None if not configured
        """
        return cls._FLAGS.get(feature)

    @classmethod
    def is_enabled_for_stage(cls, feature: Feature, min_stage: Stage) -> bool:
        """Check if feature is enabled for a minimum stage.
        Args:
            feature: The feature to check
            min_stage: Minimum required stage
        Returns:
            True if feature stage >= min_stage
        """
        current_stage = cls.get_stage(feature)
        if not current_stage:
            return False
        stage_order = {Stage.DEV: 0, Stage.BETA: 1, Stage.GA: 2}
        return stage_order.get(current_stage, -1) >= stage_order.get(min_stage, 999)

    @classmethod
    def is_dev(cls, feature: Feature) -> bool:
        """Check if feature is in dev stage."""
        return cls.get_stage(feature) == Stage.DEV

    @classmethod
    def is_beta(cls, feature: Feature) -> bool:
        """Check if feature is in beta stage."""
        return cls.get_stage(feature) == Stage.BETA

    @classmethod
    def is_ga(cls, feature: Feature) -> bool:
        """Check if feature is in GA stage."""
        return cls.get_stage(feature) == Stage.GA

    @classmethod
    def get_all_flags(cls) -> Dict[Feature, Stage]:
        """Get all feature flags."""
        return cls._FLAGS.copy()

    @classmethod
    def get_feature_config(
        cls, feature: Feature, config_section: str
    ) -> Dict[str, str]:
        """Get configuration dictionary for a feature at its current stage.
        Args:
            feature: The feature to get config for
            config_section: Configuration section to retrieve
        Returns:
            Configuration dictionary for the specified section
        """
        current_stage = cls.get_stage(feature)
        if not current_stage:
            return {}

        feature_configs = cls._FEATURE_CONFIGS.get(feature, {})
        stage_config = feature_configs.get(current_stage, {})
        return stage_config.get(config_section, {})
