import difflib
import re
from typing import Any, Callable, Dict, List

from aws_idr_customer_cli.clients.ec2 import BotoEc2Manager
from aws_idr_customer_cli.exceptions import ValidationError

EQUAL_TO = "="
PIPE = "|"
COMMA = ","


class Validate:

    def __init__(self, ec2_manager: BotoEc2Manager) -> None:
        self.ec2_manager = ec2_manager

    EMAIL_PATTERN = re.compile(
        r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*\.[a-zA-Z]{2,}$"
    )

    AWS_TAG_PATTERN = re.compile(r"^[a-zA-Z0-9\s_.:/=+\-@]*$")

    AWS_REGION_PATTERN = re.compile(r"^[a-z]{2,}-[a-z]+-\d+$")

    ALARM_ARN_PATTERN = re.compile(
        r"^arn:aws:cloudwatch:[a-z]{2,}-[a-z]+-\d+:\d{12}:alarm:.+$"
    )

    @staticmethod
    def required(value: Any) -> Any:
        """Ensure value is not empty."""
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValidationError("This field is required")
        return value

    @staticmethod
    def string(value: Any, min_len: int = 1, max_len: int = 100) -> str:
        """Validate and trim string."""
        if not isinstance(value, str):
            raise ValidationError(f"Must be text, got {type(value).__name__}")

        clean = value.strip()
        if len(clean) < min_len:
            raise ValidationError(f"Must be at least {min_len} characters")
        if len(clean) > max_len:
            raise ValidationError(f"Must be less than {max_len} characters")

        return clean

    @staticmethod
    def email(value: Any) -> str:
        """Validate email format with regex and normalize to lowercase."""
        if not isinstance(value, str):
            raise ValidationError("Email must be text")

        clean = value.strip().lower()
        if not Validate.EMAIL_PATTERN.match(clean):
            raise ValidationError("Invalid email format")

        return clean

    @staticmethod
    def phone(value: Any) -> str:
        """Validate phone format, preserving + and - characters."""
        if not isinstance(value, str):
            raise ValidationError("Phone must be text")

        clean = value.strip()
        digits_only = re.sub(r"\D", "", clean)

        if len(digits_only) < 8:
            raise ValidationError("Phone must have at least 8 digits")
        if len(digits_only) > 15:
            raise ValidationError("Phone must have no more than 15 digits")

        return clean

    @staticmethod
    def escalation_sequence(sequence: List[int], max_contact_id: int) -> List[int]:
        """Validate escalation sequence."""
        if not sequence:
            raise ValidationError(
                "Escalation sequence must contain at least one contact ID"
            )

        for contact_id in sequence:
            if not isinstance(contact_id, int):
                raise ValidationError(
                    f"Contact ID must be integer, got {type(contact_id).__name__}"
                )
            if contact_id < 0 or contact_id >= max_contact_id:
                raise ValidationError(
                    f"Contact ID {contact_id} not found (valid range: 0-{max_contact_id - 1})"
                )

        return sequence

    @staticmethod
    def aws_tag_key(value: Any) -> str:
        """Validate AWS tag key according to AWS rules."""
        if not isinstance(value, str):
            raise ValidationError("Tag key must be text")

        clean = value.strip()

        # Length validation (1-128 characters)
        if len(clean) < 1:
            raise ValidationError("Tag key cannot be empty")
        if len(clean) > 128:
            raise ValidationError("Tag key must be 128 characters or less")

        # AWS reserved prefix check
        if clean.lower().startswith("aws:"):
            raise ValidationError("Tag key cannot start with 'aws:' (reserved for AWS)")

        # Character validation
        if not Validate.AWS_TAG_PATTERN.match(clean):
            raise ValidationError(
                "Tag key contains invalid characters. Allowed: letters, numbers, spaces, _.:/=+-@"
            )

        return clean

    @staticmethod
    def aws_tag_value(value: Any) -> str:
        """Validate AWS tag value according to AWS rules."""
        if not isinstance(value, str):
            raise ValidationError("Tag value must be text")

        clean = value.strip()

        # Length validation (0-256 characters, can be empty)
        if len(clean) > 256:
            raise ValidationError("Tag value must be 256 characters or less")

        # Character validation (only if not empty)
        if clean and not Validate.AWS_TAG_PATTERN.match(clean):
            raise ValidationError(
                "Tag value contains invalid characters. Allowed: letters, numbers, spaces, _.:/=+-@"
            )

        return clean

    @staticmethod
    def aws_tag_values(value: Any) -> List[str]:
        """
        Validate AWS tag values for filtering (supports single value or list).
        Converts single string to list for consistency with AWS API.
        """
        if isinstance(value, str):
            # Single value - convert to list
            clean_value = Validate.aws_tag_value(value.strip())
            return [clean_value] if clean_value else []

        elif isinstance(value, (list, tuple)):
            # Multiple values - validate each
            clean_values = []
            for v in value:
                if isinstance(v, str):
                    clean_v = Validate.aws_tag_value(v.strip())
                    if clean_v:  # Only add non-empty values
                        clean_values.append(clean_v)
                else:
                    raise ValidationError(
                        f"Tag value must be string, got {type(v).__name__}"
                    )

            if not clean_values:
                raise ValidationError("At least one valid tag value is required")

            return clean_values

        else:
            raise ValidationError("Tag values must be string or list of strings")

    @staticmethod
    def aws_tag_filter_pairs(value: Any) -> List[Dict[str, Any]]:
        """
        Parse tag pairs into AWS filter format.

        Input formats supported:
        - "key1=value1,key2=value2" → Single values
        - "Environment=prod|staging,Team=backend" → Multiple values using |
        """
        if not isinstance(value, str):
            raise ValidationError("Tag filters must be text")

        clean = value.strip()
        if not clean:
            return []

        filters = []
        pairs = [pair.strip() for pair in clean.split(COMMA)]

        for pair in pairs:
            if not pair:
                continue

            if EQUAL_TO not in pair:
                raise ValidationError(
                    f"Invalid tag format: '{pair}'. Use key=value format"
                )

            # Split only on first = to allow = in values
            key, values_str = pair.split(EQUAL_TO, 1)

            # Validate key
            validated_key = Validate.aws_tag_key(key)

            # Handle multiple values separated by |
            if PIPE in values_str:
                value_list = [v.strip() for v in values_str.split(PIPE)]
            else:
                value_list = [values_str.strip()]

            # Validate values
            validated_values = Validate.aws_tag_values(value_list)

            filters.append({"Name": validated_key, "Values": validated_values})

        return filters

    def aws_region(self, value: str) -> str:
        """
        Validate AWS region format and optionally check existence.

        Args:
            value: Region string to validate
            check_exists: If True, check if region actually exists via AWS API

        Returns:
            Clean region string (lowercase)
        """
        if not isinstance(value, str):
            raise ValidationError("AWS region must be text")

        clean_region = value.strip().lower()

        if not clean_region:
            raise ValidationError("AWS region cannot be empty")

        # Format validation
        if not Validate.AWS_REGION_PATTERN.match(clean_region):
            raise ValidationError(
                f"Invalid AWS region format: '{clean_region}'. "
                f"Expected format: us-east-1, eu-west-2, ap-southeast-1, etc."
            )

        self._check_aws_region_exists(region=clean_region)
        return clean_region

    def aws_regions(self, value: str) -> List[str]:
        """
        Validate multiple AWS regions from comma-separated string.

        Args:
            value: Comma-separated region string to validate

        Returns:
            List of clean region strings (lowercase, deduplicated)
        """
        if not isinstance(value, str):
            raise ValidationError("Regions must be text")

        clean = value.strip()
        if not clean:
            raise ValidationError("At least one region is required")

        region_list = [r.strip().lower() for r in clean.split(",") if r.strip()]

        if not region_list:
            raise ValidationError("At least one valid region is required")

        # Get all valid regions in one API call
        valid_regions = self.get_valid_regions()

        # Validate all regions against the cached list
        validated_regions = []
        for region in region_list:
            # Format validation
            if not Validate.AWS_REGION_PATTERN.match(region):
                raise ValidationError(
                    f"Invalid AWS region format: '{region}'. "
                    f"Expected format: us-east-1, eu-west-2, ap-southeast-1, etc."
                )

            # Existence validation
            if region not in valid_regions:
                suggestions = difflib.get_close_matches(
                    region, valid_regions, n=3, cutoff=0.6
                )
                error_msg = f"AWS region '{region}' does not exist."
                if suggestions:
                    error_msg += f" Did you mean: {', '.join(suggestions)}?"
                raise ValidationError(error_msg)

            # Add to validated list (deduplicated)
            if region not in validated_regions:
                validated_regions.append(region)

        return validated_regions

    def get_valid_regions(self) -> List[str]:
        regions = self.ec2_manager.get_available_regions()
        return list(regions)

    def _check_aws_region_exists(self, region: str) -> None:
        """Check if AWS region exists by querying AWS API."""

        valid_regions = self.get_valid_regions()

        if region not in valid_regions:
            suggestions = difflib.get_close_matches(
                region, list(valid_regions), n=3, cutoff=0.6
            )

            error_msg = f"AWS region '{region}' does not exist."
            if suggestions:
                error_msg += f" Did you mean: {', '.join(suggestions)}?"

            raise ValidationError(error_msg)

    @staticmethod
    def chain(value: Any, *validators: Callable[[Any], Any]) -> Any:
        """Apply multiple validators in sequence."""
        result = value
        for validator in validators:
            result = validator(result)
        return result


# Contact-specific validators - return Any and let downstream handle types
def validate_contact_name(value: Any) -> Any:
    """Validate contact name: 2-100 chars."""
    return Validate.chain(
        value, Validate.required, lambda x: Validate.string(x, min_len=2, max_len=100)
    )


def validate_contact_email(value: Any) -> Any:
    """Validate contact email."""
    return Validate.chain(value, Validate.required, Validate.email)


def validate_contact_phone(value: Any) -> str:
    """Validate contact phone: optional, but validate format if provided."""
    if not value or (isinstance(value, str) and not value.strip()):
        return ""
    result = Validate.chain(value, Validate.phone)
    return str(result)


def validate_escalation_email_unique(value: Any, primary_contact: Any) -> Any:
    """Validate escalation email and ensure it's different from primary."""
    clean_email = validate_contact_email(value)

    if (
        primary_contact
        and hasattr(primary_contact, "email")
        and primary_contact.email == clean_email
    ):
        raise ValidationError(
            "Escalation contact email cannot be the same as primary contact email. "
            "Please provide a different email address."
        )

    return clean_email


def validate_escalation_phone_unique(value: Any, primary_contact: Any) -> Any:
    """Validate escalation phone and ensure it's different from primary."""
    clean_phone = validate_contact_phone(value)

    if (
        primary_contact
        and hasattr(primary_contact, "phone")
        and primary_contact.phone != ""
        and primary_contact.phone == clean_phone
    ):
        raise ValidationError(
            "Escalation contact phone cannot be the same as primary contact phone. "
            "Please provide a different phone number."
        )

    return clean_phone


def validate_alarm_arns(validator: Validate, arns: List[str]) -> List[str]:
    """Validate CloudWatch alarm ARNs."""
    if not arns:
        raise ValidationError("At least one alarm ARN is required")

    validated_arns = set()
    for arn in arns:
        arn = arn.strip()
        if not arn:
            continue

        if not validator.ALARM_ARN_PATTERN.match(arn):
            raise ValidationError(
                f"Invalid alarm ARN format: {arn}. "
                "Expected format: arn:aws:cloudwatch:region:account:alarm:alarm-name"
            )
        validated_arns.add(arn)

    if not validated_arns:
        raise ValidationError("At least one valid alarm ARN is required")

    return list(validated_arns)
