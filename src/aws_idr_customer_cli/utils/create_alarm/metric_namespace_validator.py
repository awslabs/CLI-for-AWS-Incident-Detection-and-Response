from typing import Dict, List

from injector import inject

from aws_idr_customer_cli.data_accessors.cloudwatch_metrics_accessor import (
    CloudWatchMetricsAccessor,
)
from aws_idr_customer_cli.utils.constants import MetricType
from aws_idr_customer_cli.utils.create_alarm.conditional_metric_validator import (
    ConditionalMetricValidator,
)


class MetricNamespaceValidator:
    """Validates CloudWatch namespace availability for ECS and EKS services,
    and validates specific metric existence for CONDITIONAL and NON-NATIVE metrics.
    """

    CI_NAMESPACE_CONFIG = {
        "ecs": ["ECS/ContainerInsights"],
        "eks": ["ContainerInsights", "ContainerInsights/Prometheus"],
    }

    @inject
    def __init__(
        self,
        metrics_accessor: CloudWatchMetricsAccessor,
        conditional_validator: ConditionalMetricValidator,
    ) -> None:
        self.metrics_accessor = metrics_accessor
        self.conditional_validator = conditional_validator
        self._namespace_cache: Dict[str, bool] = {}
        self._all_ci_namespaces = frozenset(
            namespace
            for namespaces in self.CI_NAMESPACE_CONFIG.values()
            for namespace in namespaces
        )

    def validate_service_namespaces(self, service_type: str, region: str) -> List[str]:
        """Validate which Container Insights/Prometheus namespaces are available."""
        ci_namespaces = self.CI_NAMESPACE_CONFIG.get(service_type, [])
        if not ci_namespaces:
            return []

        available_ci_namespaces = []
        for namespace in ci_namespaces:
            if self._check_namespace_exists(namespace, region):
                available_ci_namespaces.append(namespace)

        return available_ci_namespaces

    def _check_namespace_exists(self, namespace: str, region: str) -> bool:
        """Check if CloudWatch namespace exists and has metrics."""
        cache_key = f"{namespace}:{region}"

        if cache_key in self._namespace_cache:
            return self._namespace_cache[cache_key]

        try:
            metrics = self.metrics_accessor.list_metrics_by_namespace(namespace, region)
            exists = len(metrics) > 0
            self._namespace_cache[cache_key] = exists
            return exists

        except Exception:
            self._namespace_cache[cache_key] = False
            return False

    def filter_templates_by_ci_namespaces(
        self, templates: List[Dict], available_ci_namespaces: List[str]
    ) -> List[Dict]:
        """Filter templates to include non-CI + available CI templates."""
        if not templates:
            return []

        filtered_templates = []
        available_set = set(available_ci_namespaces)

        for template in templates:
            namespace = template.get("configuration", {}).get("Namespace")

            if namespace not in self._all_ci_namespaces:
                filtered_templates.append(template)
            elif namespace in available_set:
                filtered_templates.append(template)

        return filtered_templates

    def validate_metric_exists(
        self,
        namespace: str,
        metric_name: str,
        dimensions: List[Dict[str, str]],
        region: str,
        metric_type: str,
        resource_arn: str,
    ) -> bool:
        """
        Check if specific CloudWatch metric exists.

        Routes validation based on metric_type:
        - CONDITIONAL: Validates via both list_metrics API and resource configuration check
        - NON-NATIVE: Validates via CloudWatch list_metrics API

        Args:
            namespace: CloudWatch namespace
            metric_name: Metric name
            dimensions: List of dimension filters
            region: AWS region code
            metric_type: "CONDITIONAL" or "NON-NATIVE"
            resource_arn: Resource ARN for CONDITIONAL validation

        Returns:
            bool: True if metric/config exists, False otherwise
        """
        try:
            # Call CloudWatch API
            client = self.metrics_accessor.get_client(region=region)
            response = client.list_metrics(
                Namespace=namespace,
                MetricName=metric_name,
                Dimensions=dimensions,
            )

            if metric_type == MetricType.CONDITIONAL.value and not response.get(
                "Metrics"
            ):
                return bool(
                    self.conditional_validator.validate_metric_exists(
                        metric_name, resource_arn, region
                    )
                )
            else:
                return len(response.get("Metrics", [])) > 0

        except Exception as e:
            # Log error and return False
            self.metrics_accessor.logger.error(
                f"Error checking metric {metric_name} in {namespace}: {str(e)}"
            )
            return False
