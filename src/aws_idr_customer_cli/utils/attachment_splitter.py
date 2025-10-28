"""Utility for splitting large JSON attachments for AWS Support cases.

AWS Support API Limits:
- Maximum attachment size: 5 MB (5120 KB) per attachment
- Maximum alarms per attachment: 300 alarms
- Maximum attachments per attachment set: 3 attachments
- Solution: Create multiple attachment sets, each added as separate communication to the case

Splitting Strategy:
- Splits JSON into parts of ≤3 attachments each (AWS limit per attachment set)
- Each attachment is ≤5MB (AWS limit per attachment)
- Each attachment contains ≤300 alarms (service limit)
- Multiple attachment sets are added as separate communications with retry logic
- Retry: 5 attempts, 20s initial delay, 1.5x exponential backoff for rate limiting

ARN-Based Splitting Logic:
- alarm_creation: superset containing all alarms
- alarm_validation & alarm_ingestion: subsets (validated/ingested alarms only)
- alarm_validation and alarm_ingestion always have identical ARN sets
- Splitting maintains logical consistency: validation/ingestion filtered by creation ARNs
- Redundant keys (account_id, status, workload_onboard, etc.) duplicated in all parts

Algorithm:
1. Check if JSON ≤5MB AND ≤300 alarms → return single attachment
2. Calculate parts needed to keep each ≤5MB AND ≤300 alarms
3. Split alarm_creation ARNs into N chunks
4. For each chunk, filter alarm_validation/alarm_ingestion to matching ARNs only
5. Verify each part ≤5MB, increase part count if needed
6. Group parts into batches of 3 (max per attachment set)

Example with 5 alarms split into 2 parts:
  Original:
    alarm_creation: [arn1, arn2, arn3, arn4, arn5]
    alarm_validation: [arn1, arn4, arn5]
    alarm_ingestion: [arn1, arn4, arn5]

  Part 1 (attachments 1-3):
    alarm_creation: [arn1, arn2, arn3]
    alarm_validation: [arn1]
    alarm_ingestion: [arn1]

  Part 2 (attachments 4-6):
    alarm_creation: [arn4, arn5]
    alarm_validation: [arn4, arn5]
    alarm_ingestion: [arn4, arn5]
"""

import json
from typing import Any, Dict, List, Set

from aws_idr_customer_cli.utils.constants import CommandType

MAX_ATTACHMENT_SIZE_KB = 5000  # 5 MB(leaving some buffer)
MAX_ALARMS_PER_PART = 300  # Service limit for alarm count per attachment


def get_json_size_kb(data: str) -> float:
    """Calculate size of JSON string in KB."""
    return len(data.encode("utf-8")) / 1024


def split_json_for_attachments(
    json_content: str,
    max_size_kb: float = MAX_ATTACHMENT_SIZE_KB,
    command_type: str = CommandType.WORKLOAD_REGISTRATION.value,
) -> List[Dict[str, str]]:
    """Split JSON content into multiple attachments if size exceeds AWS limit.

    AWS Support API enforces a 5MB (5120 KB) limit per attachment and 300 alarms
    per attachment. This function splits large JSON files while
    maintaining logical consistency of alarm data through ARN-based filtering.

    Args:
        json_content: JSON string containing workload configuration
        max_size_kb: Maximum size in KB per attachment (default: 5120 KB = 5 MB)
        command_type: Command type for filename (e.g., "alarm_creation", "workload_onboarding")

    Returns:
        List of attachment dicts with 'fileName' and 'data' keys.
        Single attachment if size ≤5MB AND ≤300 alarms, multiple attachments otherwise.

    Example:
        >>> json_str = '{"alarm_creation": [...], "account_id": "123"}'
        >>> attachments = split_json_for_attachments(json_str, command_type="alarm_creation")
        >>> len(attachments)  # Returns 1 if <5MB, 2+ if >5MB
    """
    state = json.loads(json_content)
    alarm_count = len(state.get("alarm_creation") or [])

    # Normalize command_type to use underscores
    command_type = command_type.replace("-", "_")

    # Extract workload name and account from state
    workload_name = ""
    if state.get("workload_onboard") and state["workload_onboard"].get("name"):
        workload_name = (
            state["workload_onboard"]["name"].replace(" ", "_").replace("-", "_")
        )

    account_id = state.get("account_id", "")

    # Return single file if both constraints satisfied (no splitting needed)
    if (
        get_json_size_kb(json_content) <= max_size_kb
        and alarm_count <= MAX_ALARMS_PER_PART
    ):
        filename = (
            f"{workload_name}_{account_id}_{command_type}.json"
            if workload_name
            else f"{command_type}.json"
        )
        return [{"fileName": filename, "data": json_content}]

    # Split into 2+ files when either constraint breached
    splitter = _JsonSplitter(state, max_size_kb)
    splitter = _JsonSplitter(
        state, max_size_kb, command_type, workload_name, account_id
    )
    return splitter.split()


class _JsonSplitter:
    """Handles ARN-based splitting of large JSON files.

    This class implements splitting algorithm that:
    1. Separates splittable arrays (alarm_creation, alarm_validation, alarm_ingestion)
       from non-splittable data (account_id, workload_onboard, etc.)
    2. Splits alarm_creation into N equal chunks
    3. Filters alarm_validation and alarm_ingestion to only include alarms
       whose ARNs appear in each alarm_creation chunk
    4. Duplicates non-splittable data in every part for completeness

    The algorithm ensures logical consistency: if an alarm appears in alarm_creation
    for a part, its corresponding validation/ingestion data (if any) will also appear
    in that same part.
    """

    def __init__(
        self,
        state: Dict[str, Any],
        max_size_kb: float,
        command_type: str = CommandType.WORKLOAD_REGISTRATION.value,
        workload_name: str = "",
        account_id: str = "",
    ):
        """Initialize splitter with workload state and size limit.

        Args:
            state: Parsed JSON dict containing workload configuration
            max_size_kb: Maximum size in KB per attachment part
            command_type: Command type for filename prefix
            workload_name: Workload name for filename
            account_id: Account ID for filename

        State Structure:
            {
                "account_id": "...",           # Non-splittable (duplicated in all parts)
                "workload_onboard": {...},     # Non-splittable (duplicated in all parts)
                "alarm_creation": [...],       # Splittable (divided into chunks)
                "alarm_validation": [...],     # Splittable (filtered by ARN)
                "alarm_ingestion": {           # Splittable (filtered by ARN)
                    "onboarding_alarms": [...]
                }
            }
        """
        self.max_size_kb = max_size_kb
        self.command_type = command_type
        self.workload_name = workload_name
        self.account_id = account_id
        self.splittable_keys = ["alarm_creation", "alarm_ingestion", "alarm_validation"]

        # Extract non-splittable data (will be duplicated in every part)
        self.base_state = {
            k: v for k, v in state.items() if k not in self.splittable_keys
        }

        # Extract splittable arrays (handle None values with 'or []')
        self.alarm_creation = state.get("alarm_creation") or []
        self.alarm_validation = state.get("alarm_validation") or []

        # Handle nested alarm_ingestion structure
        alarm_ingestion = state.get("alarm_ingestion")
        if alarm_ingestion and isinstance(alarm_ingestion, dict):
            self.alarm_ingestion_base = alarm_ingestion
            self.alarm_ingestion_list = alarm_ingestion.get("onboarding_alarms") or []
        else:
            self.alarm_ingestion_base = None
            self.alarm_ingestion_list = []

    def split(self) -> List[Dict[str, str]]:
        """Split JSON into minimum number of parts where each part ≤max_size_kb and ≤300 alarms.

        Dual Constraint Algorithm:
        1. Calculate parts needed for size: max(2, base_state_size / 5120 + 1)
        2. Calculate parts needed for alarm count: ceil(total_alarms / 300)
        3. Start with max(size_parts, alarm_parts) to satisfy both constraints
        4. Iteratively verify all parts ≤5MB, increase if needed

        Example with 500 alarms (~3MB total):
            Step 1: base_state = 1MB, so num_parts_for_size = 2
            Step 2: 500 alarms, so num_parts_for_alarms = ceil(500/300) = 2
            Step 3: num_parts = max(2, 2) = 2
            Step 4: Try 2 parts (250 alarms each, ~1.5MB each)
                    Both constraints satisfied ✓
            Step 5: Return 2 parts

        Example with 50 alarms (~8MB total):
            Step 1: base_state = 2MB, so num_parts_for_size = 2
            Step 2: 50 alarms, so num_parts_for_alarms = 1
            Step 3: num_parts = max(2, 1) = 2
            Step 4: Try 2 parts (25 alarms each, ~4MB each)
                    Both constraints satisfied ✓
            Step 5: Return 2 parts

        Returns:
            List of attachment dicts, each with 'fileName' and 'data' keys.
            Minimum number of parts needed to satisfy both constraints.
        """
        # Calculate starting point for BOTH constraints
        base_state_size_kb = get_json_size_kb(json.dumps(self.base_state))
        num_parts_for_size = max(2, int(base_state_size_kb / self.max_size_kb) + 1)
        num_parts_for_alarms = (
            len(self.alarm_creation) + MAX_ALARMS_PER_PART - 1
        ) // MAX_ALARMS_PER_PART
        num_parts = max(num_parts_for_size, num_parts_for_alarms)

        # Iteratively increase parts until all parts fit within size limit
        while num_parts <= len(self.alarm_creation):
            attachments = self._create_parts(num_parts)

            # Check if ALL parts are within size limit
            if all(
                get_json_size_kb(att["data"]) <= self.max_size_kb for att in attachments
            ):
                return attachments  # Found optimal solution

            num_parts += 1  # Try more parts

        # Fallback: split into individual alarms (1 alarm per part)
        # This is guaranteed to work but creates maximum number of parts
        return self._create_parts(len(self.alarm_creation))

    def _create_parts(self, num_parts: int) -> List[Dict[str, str]]:
        """Create N parts by chunking alarm_creation and filtering others by ARN.

        This method implements the core ARN-based splitting logic:

        1. Divide alarm_creation into N equal chunks
           - chunk_size = ceil(total_alarms / num_parts)
           - Example: 150 alarms, 2 parts → chunk_size = 75

        2. For each chunk:
           a. Extract ARNs from alarms in this chunk
           b. Create part_state with:
              - All base_state data (account_id, workload_onboard, etc.)
              - This chunk of alarm_creation
              - Filtered alarm_validation (only alarms with ARNs in this chunk)
              - Filtered alarm_ingestion (only alarms with ARNs in this chunk)

        3. Serialize each part to JSON and create attachment dict

        ARN Filtering Example:
            alarm_creation chunk: [
                {"alarm_arn": "arn1", ...},
                {"alarm_arn": "arn2", ...},
                {"alarm_arn": "arn3", ...}
            ]

            chunk_arns = {"arn1", "arn2", "arn3"}

            alarm_validation (full): [
                {"alarm_arn": "arn1", ...},  # ✓ Included (arn1 in chunk)
                {"alarm_arn": "arn4", ...},  # ✗ Excluded (arn4 not in chunk)
                {"alarm_arn": "arn2", ...}   # ✓ Included (arn2 in chunk)
            ]

            alarm_validation (filtered): [
                {"alarm_arn": "arn1", ...},
                {"alarm_arn": "arn2", ...}
            ]

        Args:
            num_parts: Number of parts to create

        Returns:
            List of attachment dicts with sequential filenames and JSON data.
            Each part contains a subset of alarms with logical consistency maintained.
        """
        # Calculate chunk size (ceiling division to ensure all alarms included)
        chunk_size = (len(self.alarm_creation) + num_parts - 1) // num_parts
        attachments: List[Dict[str, str]] = []

        # Process each chunk
        for part_idx, i in enumerate(
            range(0, len(self.alarm_creation), chunk_size), start=1
        ):
            # Extract chunk of alarm_creation
            chunk = self.alarm_creation[i : i + chunk_size]

            # Extract ARNs from this chunk for filtering
            chunk_arns = {alarm["alarm_arn"] for alarm in chunk if "alarm_arn" in alarm}

            # Build part state with base data + this chunk + filtered arrays
            part_state: Dict[str, Any] = {
                **self.base_state,  # Duplicate non-splittable data
                "alarm_creation": chunk,
                "alarm_validation": self._filter_by_arns(
                    self.alarm_validation, chunk_arns
                ),
            }

            # Add filtered alarm_ingestion if present
            if self.alarm_ingestion_base:
                part_state["alarm_ingestion"] = {
                    **self.alarm_ingestion_base,  # Keep metadata
                    "onboarding_alarms": self._filter_by_arns(
                        self.alarm_ingestion_list, chunk_arns
                    ),
                }

            # Create attachment with sequential filename showing part X of N
            filename_parts = []
            if self.workload_name:
                filename_parts.append(self.workload_name)
            if self.account_id:
                filename_parts.append(self.account_id)
            filename_parts.append(self.command_type)
            filename_parts.append(f"part{part_idx}_{num_parts}")

            attachments.append(
                {
                    "fileName": f"{'_'.join(filename_parts)}.json",
                    "data": json.dumps(part_state, indent=2, ensure_ascii=False),
                }
            )

        return attachments

    @staticmethod
    def _filter_by_arns(
        alarms: List[Dict[str, Any]], arns: Set[str]
    ) -> List[Dict[str, Any]]:
        """Filter alarm list to only include matching ARNs."""
        return [alarm for alarm in alarms if alarm.get("alarm_arn") in arns]
