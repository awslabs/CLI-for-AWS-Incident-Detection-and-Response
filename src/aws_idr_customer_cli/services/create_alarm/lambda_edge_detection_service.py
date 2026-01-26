"""Service for detecting Lambda@Edge function associations.

This service determines whether a Lambda function is deployed as Lambda@Edge
by checking its associations with CloudFront distributions. Uses an in-memory
cache populated via parallel API calls for performance.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import Any, Dict, List, Set

from botocore.exceptions import ClientError
from injector import inject

from aws_idr_customer_cli.data_accessors.cloudfront_accessor import CloudFrontAccessor
from aws_idr_customer_cli.utils.constants import MAX_PARALLEL_WORKERS
from aws_idr_customer_cli.utils.log_handlers import CliLogger


class LambdaEdgeDetectionService:
    """Service for detecting Lambda@Edge function associations.

    Handles caching, parallel loading, and ARN matching logic for determining
    whether Lambda functions are deployed as Lambda@Edge with CloudFront.
    """

    ACCESS_DENIED_ERRORS: Set[str] = {
        "AccessDeniedException",
        "AccessDenied",
        "UnauthorizedOperation",
    }

    @inject
    def __init__(
        self,
        logger: CliLogger,
        cloudfront_accessor: CloudFrontAccessor,
    ) -> None:
        """Initialize LambdaEdgeDetectionService.

        Args:
            logger: CLI logger instance
            cloudfront_accessor: CloudFront data accessor for API calls
        """
        self.logger = logger
        self.cloudfront_accessor = cloudfront_accessor

        self._cache_loaded: bool = False
        self._lambda_edge_map: Dict[str, Set[str]] = {}
        self._map_lock: Lock = Lock()

    def is_lambda_edge_function(self, function_arn: str) -> bool:
        """Determine if Lambda function is deployed as Lambda@Edge.

        Uses in-memory cache for performance. On first call, loads all
        CloudFront distributions into cache. Subsequent calls perform
        instant in-memory lookups.

        Performance:
            - First call: ~1-2 seconds (one-time cache load)
            - Subsequent calls: <1ms (in-memory lookup)

        Args:
            function_arn: Lambda function ARN (versioned or unversioned)

        Returns:
            True if function is associated with any CloudFront distribution
        """
        try:
            if not function_arn or not function_arn.startswith("arn:aws:lambda:"):
                self.logger.warning(f"Invalid Lambda ARN format: {function_arn}")
                return False

            if not self._cache_loaded:
                self._load_cache()

            if self._cache_loaded:
                self.logger.debug(
                    "CloudFront distribution cache is populated. Retrieving..."
                )
                normalized_arn = self._normalize_lambda_arn(function_arn)
                is_edge = normalized_arn in self._lambda_edge_map

                if is_edge:
                    dist_ids = self._lambda_edge_map[normalized_arn]
                    self.logger.info(
                        f"Lambda function {function_arn} is associated with "
                        f"{len(dist_ids)} CloudFront distribution(s): "
                        f"{', '.join(sorted(dist_ids))}"
                    )
                else:
                    self.logger.debug(
                        f"Lambda function {function_arn} is not associated "
                        f"with any CloudFront distribution (cached lookup)"
                    )

                return is_edge

            self.logger.warning(
                f"CloudFront cache unavailable. Cannot determine Lambda@Edge "
                f"status for {function_arn}. Check CloudFront permissions."
            )
            return False

        except Exception as e:
            self.logger.error(
                f"Error checking Lambda@Edge for {function_arn}: {str(e)}"
            )
            return False

    def get_associated_distributions(self, function_arn: str) -> Set[str]:
        """Get CloudFront distribution IDs associated with a Lambda function.

        Args:
            function_arn: Lambda function ARN (versioned or unversioned)

        Returns:
            Set of distribution IDs, or empty set if not Lambda@Edge
        """
        if not self._cache_loaded:
            self._load_cache()

        if not self._cache_loaded:
            return set()

        normalized_arn = self._normalize_lambda_arn(function_arn)
        return self._lambda_edge_map.get(normalized_arn, set()).copy()

    def _load_cache(self) -> None:
        """Load all CloudFront distribution Lambda@Edge associations into cache.

        Uses parallel processing (ThreadPoolExecutor) to fetch distribution
        configurations concurrently, significantly improving performance for
        accounts with many distributions.

        Cache Structure:
            {
                "arn:aws:lambda:us-east-1:123:function:func-a": {"E111", "E222"},
                "arn:aws:lambda:us-east-1:123:function:func-b": {"E333"}
            }

        Error Handling:
            - Individual distribution errors: Logged, processing continues
            - Overall API errors: Cache load aborted, _cache_loaded stays False
            - Partial success: Cache populated with successful distributions
        """
        if self._cache_loaded:
            return

        try:
            self.logger.info("Loading CloudFront distribution cache...")

            distributions = self.cloudfront_accessor.list_distributions()
            distribution_ids = [d.get("Id") for d in distributions if d.get("Id")]

            self.logger.info(
                f"Found {len(distribution_ids)} distributions, "
                f"loading configurations in parallel..."
            )

            stats = self._process_distributions_in_parallel(distribution_ids)

            self._cache_loaded = True
            self._log_cache_load_summary(len(distribution_ids), stats)

        except ClientError as error:
            self._handle_cache_load_error(error)
        except Exception as error:
            self.logger.error(
                f"Unexpected error loading CloudFront cache: {str(error)}. "
                f"Falling back to non-cached lookups."
            )

    def _process_distributions_in_parallel(
        self, distribution_ids: List[str]
    ) -> Dict[str, int]:
        """Process multiple distributions concurrently using ThreadPoolExecutor.

        Args:
            distribution_ids: List of CloudFront distribution IDs to process

        Returns:
            Statistics dict with:
            - successful_count: Number of distributions processed successfully
            - failed_count: Number of distributions that failed to process
            - association_count: Total number of Lambda associations found
        """
        association_count = 0
        successful_count = 0
        failed_count = 0

        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_WORKERS) as executor:
            future_to_dist_id = {
                executor.submit(self._fetch_and_process_distribution, dist_id): dist_id
                for dist_id in distribution_ids
            }

            for future in as_completed(future_to_dist_id):
                dist_id = future_to_dist_id[future]
                try:
                    result = future.result()
                    association_count += result["associations"]
                    successful_count += 1
                except Exception as e:
                    failed_count += 1
                    self.logger.warning(
                        f"Failed to process distribution {dist_id}: {str(e)}"
                    )

        return {
            "successful_count": successful_count,
            "failed_count": failed_count,
            "association_count": association_count,
        }

    def _fetch_and_process_distribution(self, dist_id: str) -> Dict[str, int]:
        """Fetch single distribution and process Lambda@Edge associations.

        Thread-safe method designed for parallel execution. Fetches distribution
        config, extracts Lambda ARNs, and updates the shared cache.

        Args:
            dist_id: CloudFront distribution ID

        Returns:
            Dictionary with processing statistics:
            - 'associations': Number of Lambda associations found
        """
        try:
            distribution = self.cloudfront_accessor.get_distribution(dist_id)
            if not distribution:
                return {"associations": 0}

            config = distribution.get("DistributionConfig", {})
            lambda_arns = self._extract_lambda_associations(config)

            association_count = 0
            for arn in lambda_arns:
                if self._process_lambda_association(arn, dist_id):
                    association_count += 1

            return {"associations": association_count}

        except Exception as error:
            self._handle_distribution_error(dist_id, error)
            return {"associations": 0}

    def _extract_lambda_associations(self, config: Dict[str, Any]) -> List[str]:
        """Extract all Lambda@Edge ARNs from distribution configuration.

        Extracts Lambda function ARNs from:
        - Default cache behavior
        - Additional cache behaviors

        Args:
            config: CloudFront distribution configuration dict

        Returns:
            List of Lambda function ARNs found in the distribution
        """
        lambda_arns: List[str] = []

        default_cb = config.get("DefaultCacheBehavior", {})
        default_associations = default_cb.get("LambdaFunctionAssociations", {}).get(
            "Items", []
        )
        for assoc in default_associations:
            arn = assoc.get("LambdaFunctionARN", "")
            if arn:
                lambda_arns.append(arn)

        cache_behaviors = config.get("CacheBehaviors", {}).get("Items", [])
        for behavior in cache_behaviors:
            associations = behavior.get("LambdaFunctionAssociations", {}).get(
                "Items", []
            )
            for assoc in associations:
                arn = assoc.get("LambdaFunctionARN", "")
                if arn:
                    lambda_arns.append(arn)

        return lambda_arns

    def _process_lambda_association(self, lambda_arn: str, dist_id: str) -> bool:
        """Process a single Lambda@Edge association and add to cache.

        Thread-safe method that normalizes ARN and updates the shared cache map.

        Args:
            lambda_arn: Lambda function ARN (may be versioned)
            dist_id: CloudFront distribution ID

        Returns:
            True if association was added to cache
        """
        if not lambda_arn:
            return False

        normalized_arn = self._normalize_lambda_arn(lambda_arn)

        with self._map_lock:
            if normalized_arn not in self._lambda_edge_map:
                self._lambda_edge_map[normalized_arn] = set()
            self._lambda_edge_map[normalized_arn].add(dist_id)

        return True

    def _normalize_lambda_arn(self, function_arn: str) -> str:
        """Normalize Lambda ARN by removing version suffix.

        CloudFront stores versioned Lambda@Edge ARNs (e.g., :function:name:1).
        This method strips version to enable consistent matching.

        Args:
            function_arn: Lambda ARN (versioned or unversioned)

        Returns:
            Unversioned Lambda ARN

        Examples:
            arn:aws:lambda:us-east-1:123:function:my-func:1
            -> arn:aws:lambda:us-east-1:123:function:my-func

            arn:aws:lambda:us-east-1:123:function:my-func
            -> arn:aws:lambda:us-east-1:123:function:my-func (unchanged)
        """
        parts = function_arn.split(":")
        if len(parts) >= 8 and parts[-1].isdigit():
            return ":".join(parts[:-1])
        return function_arn

    def _handle_distribution_error(self, dist_id: str, error: Exception) -> None:
        """Handle errors that occur during distribution processing.

        Args:
            dist_id: CloudFront distribution ID that failed
            error: Exception that occurred
        """
        if isinstance(error, ClientError):
            error_code = error.response.get("Error", {}).get("Code", "")
            if error_code == "NoSuchDistribution":
                self.logger.debug(f"Distribution {dist_id} not found during cache load")
            else:
                self.logger.warning(
                    f"Error loading distribution {dist_id}: {str(error)}"
                )
        else:
            self.logger.warning(
                f"Unexpected error processing distribution {dist_id}: {str(error)}"
            )

    def _handle_cache_load_error(self, error: ClientError) -> None:
        """Handle errors that occur during cache loading.

        Args:
            error: ClientError that occurred during cache load
        """
        error_code = error.response.get("Error", {}).get("Code", "")
        if error_code in self.ACCESS_DENIED_ERRORS:
            self.logger.warning(
                f"Access denied loading CloudFront cache: {str(error)}. "
                f"Falling back to non-cached lookups."
            )
        else:
            self.logger.error(
                f"Error loading CloudFront cache: {str(error)}. "
                f"Falling back to non-cached lookups."
            )

    def _log_cache_load_summary(self, total_count: int, stats: Dict[str, int]) -> None:
        """Log summary of cache loading results.

        Args:
            total_count: Total number of distributions found
            stats: Statistics from parallel processing with keys:
                - successful_count
                - failed_count
                - association_count
        """
        failed_count = stats["failed_count"]
        successful_count = stats["successful_count"]
        association_count = stats["association_count"]

        if failed_count > 0:
            self.logger.warning(
                f"⚠️  CloudFront cache partially loaded: "
                f"{successful_count}/{total_count} distributions, "
                f"{len(self._lambda_edge_map)} Lambda@Edge functions, "
                f"{association_count} associations "
                f"({failed_count} distributions failed)"
            )
        else:
            self.logger.info(
                f"✅ CloudFront cache loaded: {total_count} "
                f"distributions, {len(self._lambda_edge_map)} Lambda@Edge "
                f"functions, {association_count} total associations"
            )
