import json
import re
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set

import boto3
from dateutil import parser
from injector import inject

from aws_idr_customer_cli.core.decorators import retry_on_throttle
from aws_idr_customer_cli.core.interactive.ui import InteractiveUI
from aws_idr_customer_cli.data_accessors.alarm_accessor import AlarmAccessor
from aws_idr_customer_cli.utils.log_handlers import CliLogger
from aws_idr_customer_cli.utils.validate_alarm.alarm_validation_constants import (
    CRITICAL_METRICS,
    INFRASTRUCTURE_KEYWORDS,
    NON_PROD_KEYWORDS,
    SKIP_PERIOD_CHECK_METRICS,
    UNSUITABLE_METRICS,
)
from aws_idr_customer_cli.utils.validate_alarm.alarm_validation_models import (
    ValidationFlags,
)


class OnboardingStatus(Enum):
    YES = "Y"
    NO = "N"
    NEEDS_CONFIRMATION = "NCC"


@dataclass
class ValidationResult:
    alarm_arn: str
    onboarding_status: str  # Full wording explanation
    is_noisy: bool
    remarks_for_customer: List[str]
    remarks_for_idr: List[str]

    @property
    def alarm_name(self) -> str:
        """Extract alarm name from ARN."""
        return (
            self.alarm_arn.split(":")[-1] if ":" in self.alarm_arn else self.alarm_arn
        )

    @property
    def status(self) -> OnboardingStatus:
        """Extract status enum from onboarding_status string."""
        if "Approved" in self.onboarding_status or self.onboarding_status == "Y":
            return OnboardingStatus.YES
        elif (
            "Cannot be onboarded" in self.onboarding_status
            or self.onboarding_status == "N"
        ):
            return OnboardingStatus.NO
        else:
            return OnboardingStatus.NEEDS_CONFIRMATION

    @property
    def recommendations(self) -> List[str]:
        """Return empty list for backward compatibility."""
        return []

    @property
    def flags(self) -> ValidationFlags:
        """Return flags object for backward compatibility."""
        return ValidationFlags(
            is_noisy=self.is_noisy,
            has_datapoints=True,
            is_infrastructure=False,
            is_unsuitable=False,
            is_non_prod=False,
        )

    @property
    def customer_remarks(self) -> List[str]:
        """Alias for remarks_for_customer."""
        return self.remarks_for_customer

    @property
    def idr_remarks(self) -> List[str]:
        """Alias for remarks_for_idr."""
        return self.remarks_for_idr

    @property
    def noise_data(self) -> Dict[str, Any]:
        """Return empty noise data for backward compatibility."""
        return {}

    @property
    def alarm_config(self) -> Dict[str, Any]:
        """Return empty alarm config for backward compatibility."""
        return {}


class AlarmValidator:
    """Optimized alarm validator with batch processing and enhanced datapoint accuracy.

    Validates CloudWatch alarms for IDR onboarding with datapoint analysis
    to distinguish between healthy low-frequency metrics and broken alarms.

    Key Features:
    - Adaptive datapoint limits based on alarm period (handles daily/weekly metrics)
    - 14-day lookback window to capture weekly business patterns
    - Recent activity verification (48-hour window) to ensure current health
    - Publishing pattern analysis with interval consistency checks
    - Batch processing for efficient API usage

    Concurrency Model:
    - Sequential by region: Processes one region at a time
    - Concurrent within region: Fetches alarm data/history using ThreadPoolExecutor (max_workers=10)
    - Sequential validation: After data fetch, validates each alarm sequentially

    Example flow for 4 alarms in us-west-2 and 2 in us-east-1:
    1. us-west-2: Fetch all 4 alarms concurrently → Validate sequentially
    2. us-east-1: Fetch all 2 alarms concurrently → Validate sequentially

    Args:
        logger: CliLogger instance for debug output
        alarm_accessor: AlarmAccessor for CloudWatch API calls
        interactive_ui: InteractiveUI for displaying progress (optional, creates default if None)

    Returns:
        ValidationResult objects with onboarding recommendations and detailed analysis
    """

    @inject
    def __init__(
        self,
        logger: CliLogger,
        alarm_accessor: AlarmAccessor,
        interactive_ui: Optional[InteractiveUI] = None,
    ):
        self.logger = logger
        self.alarm_accessor = alarm_accessor
        self.ui = interactive_ui or InteractiveUI()

    def validate_alarms(self, alarm_arns: List[str]) -> List[ValidationResult]:
        """Batch validate alarms efficiently."""
        self.ui.display_info(f"🔍 Validating {len(alarm_arns)} alarms...")

        # Group by region for batch processing
        alarms_by_region = self._group_alarms_by_region(alarm_arns=alarm_arns)
        results = []

        for region, arns in alarms_by_region.items():
            region_results = self._validate_region_batch(region=region, alarm_arns=arns)
            results.extend(region_results)

        return results

    @staticmethod
    def _group_alarms_by_region(alarm_arns: List[str]) -> Dict[str, List[str]]:
        """Group alarms by region for efficient batch processing."""
        regions: Dict[str, List[str]] = {}
        for arn in alarm_arns:
            region = arn.split(":")[3] if ":" in arn else "us-east-1"
            regions.setdefault(region, []).append(arn)
        return regions

    def _validate_region_batch(
        self, region: str, alarm_arns: List[str]
    ) -> List[ValidationResult]:
        """Validate all alarms in a region as a batch with composite alarm support."""
        results = []

        # Use batch context manager for efficient API calls
        with self._batch_cloudwatch_operations(region=region) as (
            alarm_data_map,
            history_map,
        ):
            # Batch fetch all data
            self._batch_fetch_alarm_data(
                region=region, alarm_arns=alarm_arns, result_map=alarm_data_map
            )
            self._batch_fetch_alarm_history(
                region=region, alarm_arns=alarm_arns, result_map=history_map
            )

        # Track which alarms were found as metric alarms
        processed_arns = set()

        for arn in alarm_arns:
            self.ui.display_info(f"Processing {arn.split(':')[-1]}")

            try:
                alarm_data = alarm_data_map.get(arn)
                history = history_map.get(arn, [])

                if not alarm_data:
                    # Try composite alarm
                    composite_result = self._try_composite_alarm(arn=arn, region=region)
                    if composite_result:
                        results.append(composite_result)
                        processed_arns.add(arn)
                    else:
                        results.append(
                            self._create_error_result(arn=arn, error="Alarm not found")
                        )
                    continue

                result = self._validate_single_alarm(
                    arn=arn, alarm_data=alarm_data, history=history
                )
                results.append(result)
                processed_arns.add(arn)

            except Exception as e:
                self.logger.error(f"Validation failed for {arn}: {e}")
                results.append(self._create_error_result(arn=arn, error=str(e)))

        return results

    def _try_composite_alarm(self, arn: str, region: str) -> Optional[ValidationResult]:
        """Try to fetch and validate as composite alarm."""
        try:
            name = arn.split(":")[-1] if ":" in arn else arn
            client = self.alarm_accessor.get_client(region)

            response = client.describe_alarms(
                AlarmNames=[name], AlarmTypes=["CompositeAlarm"]
            )

            composite_alarms = response.get("CompositeAlarms", [])
            if not composite_alarms:
                return None

            composite_alarm = composite_alarms[0]
            return self._build_composite_alarm_result(composite_alarm=composite_alarm)

        except Exception as e:
            self.logger.debug(f"Not a composite alarm {arn}: {e}")
            return None

    @staticmethod
    def _build_composite_alarm_result(composite_alarm: Dict) -> ValidationResult:
        """Build validation result for composite alarm."""
        arn = composite_alarm.get("AlarmArn", "")

        return ValidationResult(
            alarm_arn=arn,
            onboarding_status="Needs Customer Confirmation - This is a composite alarm "
            "that requires manual review",
            is_noisy=False,
            remarks_for_customer=[
                "This is a composite alarm that combines multiple alarms. Manual "
                "evaluation required to ensure it represents critical business impact."
            ],
            remarks_for_idr=[
                "Composite alarm - review the alarm rule to understand dependencies. "
                "Verify all child alarms are appropriate for IDR onboarding."
            ],
        )

    @contextmanager
    def _batch_cloudwatch_operations(self, region: str):  # type: ignore[no-untyped-def]
        """Context manager for concurrent CloudWatch operations."""
        alarm_data_map: Dict[str, Dict] = {}
        history_map: Dict[str, List[Dict]] = {}

        try:
            yield alarm_data_map, history_map
        except Exception as e:
            self.logger.error(f"CloudWatch operations failed for {region}: {e}")
            raise

    def _validate_single_alarm(
        self, arn: str, alarm_data: Dict, history: List[Dict]
    ) -> ValidationResult:
        """Validate single alarm with all checks."""
        name = arn.split(":")[-1] if ":" in arn else arn
        metric_name, namespace = self._extract_metric_info(alarm_data=alarm_data)

        # Get actual metric data via API like original
        region = arn.split(":")[3] if ":" in arn else "us-east-1"
        account_id = arn.split(":")[4] if ":" in arn and len(arn.split(":")) > 4 else ""

        has_datapoints = self._has_recent_datapoints(alarm_data=alarm_data)
        if account_id and region:
            # Override with API call like original
            has_datapoints = self._get_metric_datapoints_via_api(
                alarm_data=alarm_data, region=region, account_id=account_id
            )

        # Core validation flags
        flags = {
            "is_unsuitable": metric_name in UNSUITABLE_METRICS,
            "is_infrastructure": self._is_infrastructure_alarm(
                metric_name=metric_name, namespace=namespace, alarm_data=alarm_data
            ),
            "is_non_prod": self._contains_keywords(
                text=name, keywords=NON_PROD_KEYWORDS
            ),
            "is_noisy": self._is_noisy_alarm(history=history),
            "has_datapoints": has_datapoints,
            "is_critical": namespace in CRITICAL_METRICS
            and metric_name in CRITICAL_METRICS[namespace],
            "is_alarming": alarm_data.get("StateValue") == "ALARM",
            "insufficient_data": alarm_data.get("StateValue") == "INSUFFICIENT_DATA",
            "treat_missing_data_issue": self._check_treat_missing_data_issue(
                alarm_data=alarm_data, history=history
            ),
            "is_cross_account": self._detect_cross_account_metrics(
                alarm_data=alarm_data, alarm_account_id=account_id
            ),
        }

        # Determine status with clear priority
        status = self._determine_status(flags=flags)

        # Generate remarks
        customer_remarks = self._generate_customer_remarks(flags=flags)
        idr_remarks = self._generate_idr_remarks(flags=flags, namespace=namespace)

        # Generate full status wording
        status_wording = self._generate_status_explanation(status=status)

        return ValidationResult(
            alarm_arn=arn,
            onboarding_status=status_wording,
            is_noisy=flags["is_noisy"],
            remarks_for_customer=customer_remarks,
            remarks_for_idr=idr_remarks,
        )

    @staticmethod
    def _determine_status(flags: Dict[str, bool]) -> OnboardingStatus:
        """Determine onboarding status with clear priority logic."""
        # Hard NO conditions
        if flags["is_unsuitable"] or (
            flags["is_infrastructure"] and not flags["is_critical"]
        ):
            return OnboardingStatus.NO

        # Needs confirmation conditions - matches original logic
        if (
            flags["is_noisy"]
            or flags["is_alarming"]
            or not flags["has_datapoints"]
            or flags["is_non_prod"]
            or flags["insufficient_data"]
            or flags.get("treat_missing_data_issue", False)
        ):
            return OnboardingStatus.NEEDS_CONFIRMATION

        return OnboardingStatus.YES

    @staticmethod
    def _generate_status_explanation(status: OnboardingStatus) -> str:
        """Generate full explanation for onboarding status."""
        explanations = {
            OnboardingStatus.YES: "Approved for onboarding - Alarm meets all "
            "criteria for IDR incident detection",
            OnboardingStatus.NO: "Cannot be onboarded - Alarm does not meet "
            "minimum requirements for IDR",
            OnboardingStatus.NEEDS_CONFIRMATION: "Needs Customer Confirmation "
            "- Alarm requires review and "
            "confirmation before onboarding",
        }
        return explanations.get(status, "Unknown status")

    def _is_infrastructure_alarm(
        self, metric_name: str, namespace: str, alarm_data: Dict
    ) -> bool:
        """Check if alarm monitors infrastructure metrics with full original sophistication."""
        if not metric_name and not alarm_data.get("Metrics"):
            return False

        # Check complex metrics array
        if alarm_data.get("Metrics"):
            if self._check_complex_metrics_for_infrastructure(alarm_data["Metrics"]):
                return False  # Found critical metrics, not infrastructure

        # Check direct namespace
        if namespace in CRITICAL_METRICS and metric_name in CRITICAL_METRICS[namespace]:
            return False

        # Check infrastructure keywords
        metric_name_lower = metric_name.lower() if metric_name else ""
        return any(keyword in metric_name_lower for keyword in INFRASTRUCTURE_KEYWORDS)

    def _check_complex_metrics_for_infrastructure(self, metrics: List[Dict]) -> bool:
        """Check metrics array for critical metrics that override infrastructure classification."""
        for metric in metrics:
            if not isinstance(metric, dict):
                continue

            # Handle SQL expressions
            if metric.get("Expression") and self._parse_sql_expression(
                metric["Expression"]
            ):
                return True

            # Handle regular metric stats
            metric_stat = metric.get("MetricStat")
            if metric_stat and self._check_metric_stat_critical(metric_stat):
                return True

        return False

    def _parse_sql_expression(self, expression: str) -> bool:
        """Parse SQL expression to extract metric and namespace for critical check."""
        if not ("SELECT" in expression and "FROM" in expression):
            return False

        try:
            result = self._extract_from_sql_expression(expression)
            if result is None:
                return False

            metric_name, namespace = result
            return (
                namespace in CRITICAL_METRICS
                and metric_name in CRITICAL_METRICS[namespace]
            )
        except (IndexError, AttributeError, TypeError):
            return False

    def _extract_from_sql_expression(
        self, expression: str
    ) -> Optional[tuple[str, str]]:
        """Extract metric name and namespace from SQL expression with SCHEMA support."""
        try:
            # Extract metric name from SELECT clause
            select_part = expression.split("FROM")[0]
            metric_name = None

            for func in ["MAX", "MIN", "AVG"]:
                if f"{func}(" in select_part:
                    start = select_part.find("(") + 1
                    end = select_part.find(")")
                    if start > 0 and end > start:
                        metric_name = select_part[start:end].strip()
                        break

            # Extract namespace from FROM clause with enhanced SCHEMA support
            from_part = expression.split("FROM")[1].strip()
            namespace = None

            if "SCHEMA" in from_part:
                # Handle SCHEMA("AWS/RDS", ...) format
                schema_start = from_part.find("SCHEMA(") + 7
                if schema_start > 6:
                    schema_part = from_part[schema_start:]
                    # Extract first parameter, handling quotes
                    namespace = schema_part.split(",")[0].strip(" \"'")
            elif '"' in from_part:
                # Handle regular "AWS/RDS" format
                parts = from_part.split('"')
                if len(parts) > 1:
                    namespace = parts[1]

            if metric_name and namespace:
                return metric_name, namespace

        except (IndexError, AttributeError):
            pass

        return None

    def _check_treat_missing_data_issue(
        self, alarm_data: Dict, history: List[Dict]
    ) -> bool:
        """Check for TreatMissingData breaching configuration issue.

        Detects alarms that are falsely triggering due to missing data
        being treated as breaching when the metric doesn't continuously publish.
        """
        treat_missing_data = alarm_data.get("TreatMissingData", "").lower()
        current_state = alarm_data.get("StateValue")
        has_multiple_states = self._is_noisy_alarm(history)
        has_datapoints = self._has_recent_datapoints(alarm_data)

        # Issue exists when: no datapoints + (alarming or noisy) + breaching config
        return (
            not has_datapoints
            and (current_state == "ALARM" or has_multiple_states)
            and treat_missing_data == "breaching"
        )

    @staticmethod
    def _check_metric_stat_critical(metric_stat: Dict) -> bool:
        """Check if MetricStat contains critical metrics."""
        if not metric_stat:
            return False

        metric_def = metric_stat.get("Metric", {})
        metric_name = metric_def.get("MetricName", "")
        namespace = metric_def.get("Namespace", "")

        return (
            namespace in CRITICAL_METRICS and metric_name in CRITICAL_METRICS[namespace]
        )

    def _get_metric_datapoints_via_api(
        self, alarm_data: Dict, region: str, account_id: str
    ) -> bool:
        """Get actual metric datapoints via CloudWatch API with enhanced accuracy.

        Uses adaptive datapoint limits and pattern analysis to accurately assess
        metric health for both high-frequency and low-frequency publishing patterns.

        Args:
            alarm_data: CloudWatch alarm configuration
            region: AWS region for API calls
            account_id: AWS account ID for cross-account detection

        Returns:
            bool: True if metric has healthy recent datapoints, False otherwise
        """
        try:
            # Build metric queries like original
            metric_queries = AlarmValidator._build_metric_queries(alarm_data=alarm_data)
            if not metric_queries:
                self.logger.debug()
                return self._has_recent_datapoints(alarm_data=alarm_data)

            # Extended lookback for weekly patterns, adaptive datapoint limit

            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(days=14)

            # Calculate adaptive max datapoints based on alarm period
            alarm_period = alarm_data.get("Period", 300)  # Default 5 minutes
            total_seconds = 14 * 24 * 3600  # 14 days in seconds
            theoretical_max = total_seconds // alarm_period
            # Cap at reasonable limits: min 10 for pattern analysis, max 500 for API limits
            max_datapoints = min(max(theoretical_max, 10), 500)

            self.logger.debug(
                f"Datapoint analysis: period={alarm_period}s, "
                f"max_points={max_datapoints}, lookback=14d"
            )

            # In CLI context, we'd use boto3 instead of k2_apis
            try:

                cloudwatch = boto3.client("cloudwatch", region_name=region)

                response = cloudwatch.get_metric_data(
                    MetricDataQueries=metric_queries,  # type: ignore[arg-type]
                    StartTime=start_time,
                    EndTime=end_time,
                    ScanBy="TimestampDescending",
                    MaxDatapoints=max_datapoints,
                )

                # Enhanced datapoint analysis
                for result in response.get("MetricDataResults", []):
                    values = result.get("Values", [])
                    timestamps = result.get("Timestamps", [])

                    if len(values) == 0:
                        self.logger.debug(
                            f"No datapoints found for metric query {result.get('Id', 'unknown')}"
                        )
                        continue

                    # Check for recent activity (last 48 hours)
                    recent_threshold = end_time - timedelta(hours=48)
                    recent_data = [t for t in timestamps if t >= recent_threshold]

                    self.logger.debug(
                        f"Datapoint summary: total={len(values)}, recent_48h={len(recent_data)}"
                    )

                    if len(recent_data) > 0:
                        # Has recent data - verify it's not just noise
                        if len(timestamps) >= 2:
                            # Check publishing pattern health
                            pattern_health = self._analyze_metric_publishing_pattern(
                                timestamps=timestamps, alarm_period=alarm_period
                            )
                            self.logger.debug(
                                f"Pattern health: {pattern_health['healthy']} "
                                f"(ratio: {pattern_health.get('health_ratio', 'N/A')})"
                            )
                            return bool(pattern_health["healthy"])
                        self.logger.debug(
                            "Recent data found, insufficient for pattern analysis - "
                            "assuming healthy"
                        )
                        return True

                self.logger.debug(
                    "No recent datapoints found via API, falling back to state reason"
                )

            except Exception as e:
                # Fall back to state reason analysis if API fails
                self.logger.debug(
                    f"API call failed: {e}, falling back to state reason analysis"
                )
                pass

            return self._has_recent_datapoints(alarm_data=alarm_data)

        except Exception as e:
            self.logger.debug(
                f"Datapoint analysis failed: {e}, falling back to state reason"
            )
            return self._has_recent_datapoints(alarm_data=alarm_data)

    @staticmethod
    def _build_metric_queries(alarm_data: Dict) -> List[Dict]:
        """Build metric queries like original script."""
        queries = []

        # Handle Target Tracking alarms
        alarm_name = alarm_data.get("AlarmName", "")
        if alarm_name.startswith("TargetTracking-"):
            if alarm_data.get("Metrics"):
                for metric in alarm_data["Metrics"]:
                    if metric.get("MetricStat"):
                        metric_stat = metric["MetricStat"]
                        queries.append(
                            {
                                "Id": metric.get("Id", "target0"),
                                "MetricStat": {
                                    "Metric": metric_stat["Metric"],
                                    "Period": metric_stat.get("Period", 60),
                                    "Stat": metric_stat.get("Stat", "Average"),
                                },
                                "ReturnData": True,
                            }
                        )
            return queries

        # Handle complex metric configurations
        if alarm_data.get("Metrics"):
            for idx, metric in enumerate(alarm_data["Metrics"]):
                query = {"Id": metric.get("Id", f"m{idx}")}

                if metric.get("Expression"):
                    query.update(
                        {
                            "Expression": metric["Expression"],
                            "Label": metric.get("Label", f"Expression_{idx}"),
                            "ReturnData": metric.get("ReturnData", True),
                        }
                    )
                elif metric.get("MetricStat"):
                    metric_def = metric["MetricStat"].get("Metric", {})
                    query.update(
                        {
                            "MetricStat": {
                                "Metric": {
                                    "Namespace": metric_def.get("Namespace"),
                                    "MetricName": metric_def.get("MetricName"),
                                    "Dimensions": metric_def.get("Dimensions", []),
                                },
                                "Period": metric["MetricStat"].get("Period", 60),
                                "Stat": metric["MetricStat"].get("Stat", "Average"),
                            },
                            "ReturnData": metric.get("ReturnData", False),
                        }
                    )
                queries.append(query)

        # Handle standard metric alarms
        elif alarm_data.get("Namespace") and alarm_data.get("MetricName"):
            queries.append(
                {
                    "Id": "m0",
                    "MetricStat": {
                        "Metric": {
                            "Namespace": alarm_data["Namespace"],
                            "MetricName": alarm_data["MetricName"],
                            "Dimensions": alarm_data.get("Dimensions", []),
                        },
                        "Period": alarm_data.get("Period", 60),
                        "Stat": alarm_data.get("Statistic", "Average"),
                    },
                    "ReturnData": True,
                }
            )

        return queries

    def _detect_cross_account_metrics(
        self, alarm_data: Dict, alarm_account_id: str
    ) -> bool:
        """Detect cross-account metrics like original."""
        if not alarm_account_id:
            return False

        # Check metrics array for accountId
        if alarm_data.get("Metrics"):
            for metric in alarm_data["Metrics"]:
                metric_account = metric.get("AccountId")
                if metric_account and metric_account != alarm_account_id:
                    return True

        return False

    def _extract_full_alarm_config(
        self, alarm_data: Dict, arn: str, account_id: str
    ) -> Dict[str, Any]:
        """Extract full alarm configuration like original OrderedDict output."""
        metric_name, namespace = self._extract_metric_info(alarm_data=alarm_data)

        # Extract dimensions
        dimensions_list = alarm_data.get("Dimensions", [])
        dimensions_str = (
            ", ".join([f"{dim['Name']} = {dim['Value']}" for dim in dimensions_list])
            if dimensions_list
            else ""
        )

        # Extract metrics expressions
        metrics_parts = []
        if alarm_data.get("Metrics"):
            for metric in alarm_data["Metrics"]:
                if metric.get("Expression"):
                    metrics_parts.append(
                        f"Expression: {metric['Expression']} (ID: {metric['Id']})"
                    )
                elif metric.get("MetricStat"):
                    metric_stat = metric["MetricStat"]
                    metrics_parts.append(
                        f"Metric: {metric_stat.get('Metric', {}).get('MetricName', 'unknown')} "
                        f"(ID: {metric['Id']})"
                    )

        # Detect cross-account metrics
        source_metric_account = "unknown"
        if alarm_data.get("Metrics"):
            for metric in alarm_data["Metrics"]:
                if metric.get("AccountId") and metric["AccountId"] != account_id:
                    source_metric_account = metric["AccountId"]
                    break

        return {
            "Type": "MetricAlarm",
            "AlarmArn": arn,
            "AlarmAccount": account_id or "unknown",
            "Source_Metric_Account": source_metric_account,
            "AlarmState": alarm_data.get("StateValue", "unknown"),
            "Period": str(alarm_data.get("Period", "unknown")),
            "DatapointsToAlarm": f"{alarm_data.get('DatapointsToAlarm', 'unknown')} "
            f"out of {alarm_data.get('EvaluationPeriods', 'unknown')}",
            "TreatMissingData": alarm_data.get("TreatMissingData", "unknown"),
            "Statistic": alarm_data.get("Statistic", "unknown"),
            "Threshold": alarm_data.get("Threshold", "unknown"),
            "ComparisonOperator": alarm_data.get("ComparisonOperator", "unknown"),
            "Namespace": namespace,
            "MetricName": metric_name,
            "Dimensions": dimensions_str,
            "Metrics": "\\n".join(metrics_parts) if metrics_parts else "null",
        }

    @staticmethod
    def _contains_keywords(*, text: str, keywords: Set[str]) -> bool:
        """Check if text contains any keywords."""
        if not text:
            return False
        text_words = set(text.lower().replace("-", " ").replace("_", " ").split())
        return bool(text_words.intersection(keywords))

    @staticmethod
    def _is_noisy_alarm(history: List[Dict]) -> bool:
        """Check for noisy alarm patterns with full original sophistication."""
        if not history:
            return False

        try:
            state_transitions = AlarmValidator._extract_state_transitions(
                history=history
            )
            if not state_transitions:
                return False

            metrics = AlarmValidator._analyze_noise_metrics(
                state_transitions=state_transitions
            )
            has_close_alarms = AlarmValidator._check_alarm_proximity(
                state_transitions=state_transitions
            )

            if not has_close_alarms:
                return False

            return AlarmValidator._determine_noise_level(
                metrics=metrics, state_transitions=state_transitions
            )

        except Exception:
            return False

    @staticmethod
    def _extract_state_transitions(history: List[Dict]) -> List[Dict]:
        """Extract and process state transitions from alarm history."""
        state_transitions = []
        now = datetime.now(timezone.utc)

        for item in history:
            try:
                timestamp = item.get("Timestamp")
                if isinstance(timestamp, str):

                    timestamp = parser.isoparse(timestamp)

                if not timestamp or (now - timestamp).days > 14:
                    continue

                summary = item.get("HistorySummary", "")

                if "to ALARM" in summary:
                    new_state, old_state = "ALARM", "OK"
                elif "to OK" in summary:
                    new_state, old_state = "OK", "ALARM"
                else:
                    continue

                # Extract values for swing analysis
                new_value, old_value = AlarmValidator._extract_values_from_summary(
                    summary=summary
                )

                state_transitions.append(
                    {
                        "timestamp": timestamp,
                        "new_state": new_state,
                        "old_state": old_state,
                        "new_value": new_value,
                        "old_value": old_value,
                        "has_missing_data": "no datapoints were received" in summary,
                        "hour_key": timestamp.strftime("%Y-%m-%d %H"),
                        "day_key": timestamp.strftime("%Y-%m-%d"),
                    }
                )

            except Exception:
                continue

        return sorted(state_transitions, key=lambda x: x["timestamp"])

    @staticmethod
    def _analyze_metric_publishing_pattern(timestamps: List, alarm_period: int) -> Dict:
        """Analyze metric publishing pattern for health assessment."""
        if len(timestamps) < 2:
            return {"healthy": False, "reason": "insufficient_data"}

        try:
            # Calculate intervals between datapoints
            time_diffs = []
            for i in range(len(timestamps) - 1):
                diff = (timestamps[i] - timestamps[i + 1]).total_seconds()
                time_diffs.append(diff)

            if not time_diffs:
                return {"healthy": False, "reason": "no_intervals"}

            # Expected interval based on alarm period (with tolerance for CloudWatch delays)
            expected_interval = alarm_period
            tolerance_multiplier = 3  # Allow 3x period for irregular metrics

            # Check recent intervals (last 5 or all if fewer)
            recent_intervals = time_diffs[: min(5, len(time_diffs))]

            # Count intervals that are within acceptable range
            acceptable_intervals = [
                interval
                for interval in recent_intervals
                if interval <= expected_interval * tolerance_multiplier
            ]

            # Metric is healthy if majority of recent intervals are acceptable
            health_ratio = len(acceptable_intervals) / len(recent_intervals)
            is_healthy = health_ratio >= 0.6  # 60% threshold

            return {
                "healthy": is_healthy,
                "health_ratio": health_ratio,
                "expected_interval": expected_interval,
                "recent_intervals": len(recent_intervals),
                "acceptable_intervals": len(acceptable_intervals),
            }

        except Exception:
            # On any error, default to healthy to avoid false negatives
            return {"healthy": True, "reason": "analysis_error"}

    @staticmethod
    def _extract_values_from_summary(
        summary: str,
    ) -> tuple[Optional[float], Optional[float]]:
        """Extract numeric values from alarm summary for swing analysis."""
        try:

            values = re.findall(r"\[([0-9.]+)\]", summary)
            if len(values) >= 2:
                return float(values[0]), float(values[1])
        except Exception:
            pass
        return None, None

    @staticmethod
    def _analyze_noise_metrics(state_transitions: List[Dict]) -> Dict[str, Any]:
        """Analyze noise metrics from state transitions."""
        metrics = {
            "alarm_states": 0,
            "daily_alarms": set(),
            "rapid_changes": 0,
            "value_swings": 0,
            "state_changes": 0,
            "hourly_changes": {},
            "missing_data_periods": set(),
            "consecutive_missing": 0,
            "values": [],
        }

        # Detect state metrics
        is_state_metric = any(
            [
                any(
                    keyword in item.get("HistorySummary", "")
                    for keyword in ["ConnectionState", "State", "Available", "Status"]
                )
                for item in state_transitions
            ]
        )

        last_transition = None
        for transition in state_transitions:
            AlarmValidator._update_metrics(
                metrics=metrics, transition=transition, last_transition=last_transition
            )
            last_transition = transition

        metrics["is_state_metric"] = is_state_metric
        return metrics

    @staticmethod
    def _update_metrics(
        metrics: Dict, transition: Dict, last_transition: Optional[Dict]
    ) -> None:
        """Update noise metrics for a single transition."""
        # Track basic metrics
        metrics["hourly_changes"][transition["hour_key"]] = (
            metrics["hourly_changes"].get(transition["hour_key"], 0) + 1
        )

        if transition["new_state"] == "ALARM":
            metrics["alarm_states"] += 1
            metrics["daily_alarms"].add(transition["day_key"])

        if transition["has_missing_data"]:
            metrics["missing_data_periods"].add(transition["hour_key"])
            metrics["consecutive_missing"] += 1

        if transition["new_value"] is not None:
            metrics["values"].append(transition["new_value"])

        if last_transition and transition["new_state"] != last_transition["new_state"]:
            metrics["state_changes"] += 1

            # Check for rapid changes
            time_diff = (
                transition["timestamp"] - last_transition["timestamp"]
            ).total_seconds()
            if time_diff <= 3600:
                metrics["rapid_changes"] += 1

            # Check for value swings
            AlarmValidator._check_value_swings(
                metrics=metrics, transition=transition, last_transition=last_transition
            )

    @staticmethod
    def _check_value_swings(
        metrics: Dict, transition: Dict, last_transition: Dict
    ) -> None:
        """Check for significant value swings between transitions."""
        if (
            transition["new_value"] is not None
            and last_transition["new_value"] is not None
        ):
            try:
                value_change = abs(
                    transition["new_value"] - last_transition["new_value"]
                )
                relative_change = value_change / max(
                    abs(last_transition["new_value"]), 0.1
                )
                if relative_change > 0.2:  # 20% change threshold
                    metrics["value_swings"] += 1
            except Exception:
                pass

    @staticmethod
    def _check_alarm_proximity(state_transitions: List[Dict]) -> bool:
        """Check if alarms occur within 7 days of each other."""
        alarm_times = [
            t["timestamp"] for t in state_transitions if t["new_state"] == "ALARM"
        ]
        alarm_times.sort()

        for i in range(len(alarm_times) - 1):
            if (alarm_times[i + 1] - alarm_times[i]).days <= 7:
                return True
        return False

    @staticmethod
    def _determine_noise_level(metrics: Dict, state_transitions: List[Dict]) -> bool:
        """Determine if alarm is noisy based on analyzed metrics."""
        days_monitored = len(set(t["day_key"] for t in state_transitions))
        changes_per_day = metrics["state_changes"] / max(days_monitored, 1)
        max_changes_per_hour = (
            max(metrics["hourly_changes"].values()) if metrics["hourly_changes"] else 0
        )
        missing_data_ratio = len(metrics["missing_data_periods"]) / max(
            days_monitored, 1
        )

        if metrics["is_state_metric"]:
            return any(
                [
                    (metrics["state_changes"] >= 3 and max_changes_per_hour >= 3),
                    changes_per_day >= 2,
                ]
            )
        else:
            is_noisy = any(
                [
                    metrics["rapid_changes"] >= 2,
                    metrics["value_swings"] >= 2,
                    max_changes_per_hour >= 3,
                    changes_per_day >= 2,
                    missing_data_ratio > 0.3,
                    metrics["consecutive_missing"] >= 3,
                    len(metrics["daily_alarms"]) >= 2,
                ]
            )

            # Check value variance
            if len(metrics["values"]) >= 2:
                try:

                    if statistics.variance(metrics["values"]) > 0.25:
                        is_noisy = True
                except Exception:
                    pass

            return is_noisy

    @staticmethod
    def _has_recent_datapoints(alarm_data: Dict) -> bool:
        """Check if alarm has recent datapoints with full original sophistication."""
        try:
            # Check state reason patterns
            if AlarmValidator._check_state_reason_patterns(alarm_data=alarm_data):
                return AlarmValidator._get_state_reason_result(alarm_data=alarm_data)

            # Parse state reason data
            return AlarmValidator._parse_state_reason_data(alarm_data=alarm_data)

        except Exception:
            return True  # Default assumption on error

    @staticmethod
    def _check_state_reason_patterns(alarm_data: Dict) -> bool:
        """Check if state reason contains clear datapoint indicators."""
        state_reason = alarm_data.get("StateReason", "").lower()

        # Clear no datapoints indicator
        if "no datapoints were received" in state_reason:
            return True

        # Numeric value patterns

        if re.findall(r"\[([0-9.]+)", state_reason):
            return True

        # Datapoint text patterns
        patterns = [
            ("datapoint" in state_reason and "[" in state_reason),
            ("out of the last" in state_reason and "datapoint" in state_reason),
            (
                "threshold crossed:" in state_reason
                and ("datapoint" in state_reason or "datapoints" in state_reason)
            ),
        ]

        return any(patterns)

    @staticmethod
    def _get_state_reason_result(alarm_data: Dict) -> bool:
        """Get datapoint result from state reason analysis."""
        state_reason = alarm_data.get("StateReason", "").lower()

        if "no datapoints were received" in state_reason:
            return False

        return True  # All other patterns indicate datapoints exist

    @staticmethod
    def _parse_state_reason_data(alarm_data: Dict) -> bool:
        """Parse StateReasonData JSON for datapoint information."""
        state_reason_data = alarm_data.get("StateReasonData")
        if not state_reason_data:
            return True

        try:

            state_data = json.loads(state_reason_data)

            # Check recentDatapoints
            if AlarmValidator._check_recent_datapoints(state_data=state_data):
                return True

            # Check evaluatedDatapoints
            if AlarmValidator._check_evaluated_datapoints(state_data=state_data):
                return True

        except json.JSONDecodeError:
            pass

        return True  # Default assumption

    @staticmethod
    def _check_recent_datapoints(state_data: Dict) -> bool:
        """Check recentDatapoints array for valid data."""
        recent_points = state_data.get("recentDatapoints", [])
        if not recent_points or len(recent_points) == 0:
            return False

        try:
            return any(isinstance(float(point), float) for point in recent_points)
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _check_evaluated_datapoints(state_data: Dict) -> bool:
        """Check evaluatedDatapoints array for valid data."""
        eval_points = state_data.get("evaluatedDatapoints", [])
        if not eval_points:
            return False

        for point in eval_points:
            if isinstance(point.get("value"), (int, float)) or isinstance(
                point.get("sampleCount"), (int, float)
            ):
                return True

        return False

    @staticmethod
    def _extract_metric_info(alarm_data: Dict) -> tuple[str, str]:
        """Extract metric name and namespace efficiently."""
        # Direct fields
        metric_name = alarm_data.get("MetricName", "unknown")
        namespace = alarm_data.get("Namespace", "unknown")

        # Check metrics array for composite alarms
        if metric_name == "unknown" and alarm_data.get("Metrics"):
            for metric in alarm_data["Metrics"]:
                if metric.get("MetricStat", {}).get("Metric"):
                    m = metric["MetricStat"]["Metric"]
                    metric_name = m.get("MetricName", metric_name)
                    namespace = m.get("Namespace", namespace)
                    break

        return metric_name, namespace

    @staticmethod
    def _should_skip_period_check(metric_name: str) -> bool:
        """Check if metric should skip period validation like original."""
        return metric_name in SKIP_PERIOD_CHECK_METRICS

    @staticmethod
    def _generate_recommendations(alarm_data: Dict, flags: Dict) -> List[str]:
        """Generate concise recommendations matching original logic."""
        recommendations = []

        period = alarm_data.get("Period", 0)
        metric_name = alarm_data.get("MetricName", "")

        # Skip period check for certain metrics like original
        if not AlarmValidator._should_skip_period_check(metric_name=metric_name):
            if period > 60:
                recommendations.append("Change Period to 60 for faster detection")

        datapoints = alarm_data.get("DatapointsToAlarm", 0)
        evaluation = alarm_data.get("EvaluationPeriods", 0)

        if datapoints == 1 and evaluation == 1:
            recommendations.append(
                "The alarm is configured to trigger on a single "
                "datapoint, which may cause false alarms. "
                "Change DatapointsToAlarm to 5 out of 5 "
                "evaluation periods to reduce noise."
            )
        elif datapoints < 3:
            recommendations.append(
                "Change DatapointsToAlarm to 5 out of 5 to reduce false positives"
            )

        return recommendations

    @staticmethod
    def _generate_customer_remarks(flags: Dict) -> List[str]:
        """Generate customer-facing remarks."""
        remarks = []

        if flags["is_unsuitable"]:
            remarks.append("Infrastructure metric cannot be onboarded")
        elif flags["is_infrastructure"] and not flags["is_critical"]:
            remarks.append("Level 1 infrastructure metric - not suitable for IDR")

        if flags["is_noisy"]:
            remarks.append("Alarm frequently transitions - revise threshold")

        if flags["is_alarming"]:
            remarks.append("Currently alarming - ensure it represents critical impact")

        if not flags["has_datapoints"]:
            remarks.append("No recent datapoints - validate metric configuration")

        if flags["treat_missing_data_issue"]:
            remarks.append(
                "Check if this alarm is being falsely "
                "triggered due to TreatMissingData configuration. "
                "If the metric is not expected to continuously "
                "record datapoints, update TreatMissingData to notBreaching."
            )

        return remarks

    @staticmethod
    def _generate_idr_remarks(flags: Dict, namespace: str) -> List[str]:
        """Generate IDR team remarks."""
        remarks = []

        if flags["is_non_prod"]:
            remarks.append("May be non-production - confirm business criticality")

        if flags["is_critical"]:
            remarks.append(f"Critical {namespace} metric - acceptable for IDR")

        return remarks

    @staticmethod
    def _calculate_frequency(history: List[Dict]) -> float:
        """Calculate alarm frequency per day."""
        if not history:
            return 0.0
        alarm_count = sum(
            1 for item in history if "to ALARM" in item.get("HistorySummary", "")
        )
        return alarm_count / 14.0

    def _batch_fetch_alarm_data(
        self, region: str, alarm_arns: List[str], result_map: Dict[str, Dict]
    ) -> None:
        """Fetch alarm data concurrently with controlled parallelism."""

        @retry_on_throttle(max_retries=3, initial_backoff=1)
        def fetch_single(arn: str) -> tuple[str, Optional[Dict]]:
            name = arn.split(":")[-1] if ":" in arn else arn
            try:
                return arn, self.alarm_accessor.get_alarm_by_name(
                    name=name, region=region
                )
            except Exception as e:
                self.logger.error(f"Failed to fetch {name}: {e}")
                return arn, None

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(fetch_single, arn): arn for arn in alarm_arns}
            for future in as_completed(futures):
                arn, data = future.result()
                if data:
                    result_map[arn] = data

    def _batch_fetch_alarm_history(
        self, region: str, alarm_arns: List[str], result_map: Dict[str, List[Dict]]
    ) -> None:
        """Fetch alarm history concurrently with controlled parallelism."""

        @retry_on_throttle(max_retries=3, initial_backoff=1)
        def fetch_single(arn: str) -> tuple[str, List[Dict]]:
            name = arn.split(":")[-1] if ":" in arn else arn
            try:
                client = self.alarm_accessor.get_client(region)
                end_time = datetime.utcnow()
                start_time = end_time - timedelta(days=14)

                response = client.describe_alarm_history(
                    AlarmName=name,
                    HistoryItemType="StateUpdate",
                    StartDate=start_time,
                    EndDate=end_time,
                    MaxRecords=100,
                )
                return arn, response.get("AlarmHistoryItems", [])
            except Exception as e:
                self.logger.debug(f"No history for {name}: {e}")
                return arn, []

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(fetch_single, arn): arn for arn in alarm_arns}
            for future in as_completed(futures):
                arn, history = future.result()
                result_map[arn] = history

    @staticmethod
    def _create_error_result(arn: str, error: str) -> ValidationResult:
        """Create error result for failed validations."""
        return ValidationResult(
            alarm_arn=arn,
            onboarding_status="Cannot be onboarded - Validation failed",
            is_noisy=False,
            remarks_for_customer=[f"Validation failed: {error}"],
            remarks_for_idr=[f"Technical error: {error}"],
        )
