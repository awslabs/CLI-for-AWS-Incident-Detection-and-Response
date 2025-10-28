"""Utilities for hash calculation and verification."""

import hashlib
import json
from typing import Any, Dict

from aws_idr_customer_cli.services.file_cache.data import OnboardingSubmission


def calculate_submission_hash(submission: OnboardingSubmission) -> str:
    """Calculate content-based hash for submission data integrity.

    This matches the algorithm used by FileCacheService for consistent
    hash calculation across the codebase.

    Args:
        submission: OnboardingSubmission object to hash

    Returns:
        SHA-256 hash of submission content (excluding filehash field)
    """
    submission_dict = submission.to_dict()
    submission_dict.pop("filehash", None)
    return hashlib.sha256(
        json.dumps(submission_dict, sort_keys=True, default=str).encode()
    ).hexdigest()


def calculate_dict_hash(data: Dict[str, Any]) -> str:
    """Calculate content-based hash for dictionary data.

    Args:
        data: Dictionary to hash

    Returns:
        SHA-256 hash of dictionary content (excluding filehash field)
    """
    data_copy = data.copy()
    data_copy.pop("filehash", None)
    return hashlib.sha256(
        json.dumps(data_copy, sort_keys=True, default=str).encode()
    ).hexdigest()
