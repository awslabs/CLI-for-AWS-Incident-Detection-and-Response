from typing import Dict, List

from injector import inject

from aws_idr_customer_cli.data_accessors.alarm_accessor import AlarmAccessor


class MetricNamespaceValidator:
    """Validates CloudWatch namespace availability for ECS and EKS services,
    can be extended for other services.
    """

    CI_NAMESPACE_CONFIG = {
        "ecs": ["ECS/ContainerInsights"],
        "eks": ["ContainerInsights", "ContainerInsights/Prometheus"],
    }

    @inject
    def __init__(self, alarm_accessor: AlarmAccessor) -> None:
        self.alarm_accessor = alarm_accessor
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
            metrics = self.alarm_accessor.list_metrics_by_namespace(namespace, region)
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
