from dataclasses import dataclass
from typing import Any, ClassVar, Dict, List, Optional, Union

from aws_idr_customer_cli.services.file_cache.data import ResourceArn


@dataclass
class AlarmRecommendation:
    alarm_name: str
    already_exists: Optional[bool]
    resource_arn: ResourceArn
    is_selected: bool
    alarm_description: str
    metric_name: Optional[str]  # Optional for math expression alarms
    namespace: Optional[str]  # Optional for math expression alarms
    statistic: Optional[str]  # Optional for math expression alarms
    threshold: float
    comparison_operator: str
    evaluation_periods: int
    period: int
    datapoints_to_alarm: Optional[int]
    treat_missing_data: str
    dimensions: List[Dict[str, str]]
    alarm_type: Optional[str]
    tags: Dict[str, str]
    # For math expression alarms
    metrics: Optional[List[Dict[str, Any]]] = None

    # Mapping from field names to CloudWatch API keys and display order
    _FIELD_MAPPING: ClassVar[Dict[str, Dict[str, Union[str, int]]]] = {
        "alarm_name": {"cw_key": "AlarmName", "order": 1},
        "alarm_description": {"cw_key": "AlarmDescription", "order": 2},
        "metric_name": {"cw_key": "MetricName", "order": 3},
        "namespace": {"cw_key": "Namespace", "order": 4},
        "statistic": {"cw_key": "Statistic", "order": 5},
        "period": {"cw_key": "Period", "order": 6},
        "evaluation_periods": {"cw_key": "EvaluationPeriods", "order": 7},
        "datapoints_to_alarm": {"cw_key": "DatapointsToAlarm", "order": 8},
        "threshold": {"cw_key": "Threshold", "order": 9},
        "comparison_operator": {"cw_key": "ComparisonOperator", "order": 10},
        "treat_missing_data": {"cw_key": "TreatMissingData", "order": 11},
        "dimensions": {"cw_key": "Dimensions", "order": 12},
        "metrics": {"cw_key": "Metrics", "order": 13},
    }

    # Fields to exclude for math expression alarms
    _EXCLUDED_FIELDS_FOR_MATH_EXPRESSION: ClassVar[set] = {
        "metric_name",
        "namespace",
        "statistic",
        "dimensions",
        "period",
    }

    def to_cloudwatch_dict(self) -> Dict[str, Any]:
        """Convert to CloudWatch API format with PascalCase keys."""
        result: Dict[str, Any] = {}

        # For math expression alarms, exclude individual metric fields
        is_math_expression_alarm = self.metrics is not None

        for field_name, mapping in self._FIELD_MAPPING.items():
            value = getattr(self, field_name)
            cw_key = str(mapping["cw_key"])

            # Skip None values to avoid CloudWatch API errors
            if value is None:
                continue

            # For math expression alarms, exclude individual metric fields
            if (
                is_math_expression_alarm
                and field_name in self._EXCLUDED_FIELDS_FOR_MATH_EXPRESSION
            ):
                continue

            result[cw_key] = value

        return result

    def _format_dimensions(self, dimensions: List[Dict[str, str]]) -> List[str]:
        """Format dimensions for display."""
        parts = ["    Dimensions:"]
        for dimension in dimensions:
            if isinstance(dimension, dict):
                name = dimension.get("Name", "N/A")
                value = dimension.get("Value", "N/A")
                parts.append(f"      Name: {name}")
                parts.append(f"      Value: {value}")
        return parts

    def _format_metric_dimensions(self, dimensions: List[Dict[str, str]]) -> List[str]:
        """Format metric dimensions for display."""
        parts = ["            Dimensions:"]
        for dim in dimensions:
            if isinstance(dim, dict):
                name = dim.get("Name", "N/A")
                value = dim.get("Value", "N/A")
                parts.append(f"              Name: {name}")
                parts.append(f"              Value: {value}")
        return parts

    def _format_metric_stat(self, metric_stat: Dict[str, Any]) -> List[str]:
        """Format MetricStat for display."""
        parts = ["        MetricStat:"]
        for sub_key, sub_val in metric_stat.items():
            if sub_key == "Metric" and isinstance(sub_val, dict):
                parts.append(f"          {sub_key}:")
                for metric_key, metric_val in sub_val.items():
                    if metric_key == "Dimensions" and isinstance(metric_val, list):
                        parts.extend(self._format_metric_dimensions(metric_val))
                    else:
                        parts.append(f"            {metric_key}: {metric_val}")
            else:
                parts.append(f"          {sub_key}: {sub_val}")
        return parts

    def _format_metrics(self, metrics: List[Dict[str, Any]]) -> List[str]:
        """Format Metrics array for display."""
        parts = ["    Metrics:"]
        for i, metric in enumerate(metrics):
            parts.append(f"      Metric {i + 1}:")
            if isinstance(metric, dict):
                for key, val in metric.items():
                    if key == "MetricStat" and isinstance(val, dict):
                        parts.extend(self._format_metric_stat(val))
                    else:
                        parts.append(f"        {key}: {val}")
        return parts

    def alarm_configuration_to_formatted_string(self) -> str:
        """Format alarm configuration details for display."""
        details_parts = [
            f"Region: {self.resource_arn.region}",
            "Alarm Configuration:",
        ]

        # Sort fields by display order
        sorted_fields = sorted(
            self._FIELD_MAPPING.items(), key=lambda x: int(x[1]["order"])
        )

        for field_name, mapping in sorted_fields:
            value = getattr(self, field_name)
            cw_key = str(mapping["cw_key"])

            if not value:
                continue

            if cw_key == "Dimensions" and isinstance(value, list):
                details_parts.extend(self._format_dimensions(value))
            elif cw_key == "Metrics" and isinstance(value, list):
                details_parts.extend(self._format_metrics(value))
            else:
                details_parts.append(f"    {cw_key}: {value}")

        return "\n    ".join(details_parts)
