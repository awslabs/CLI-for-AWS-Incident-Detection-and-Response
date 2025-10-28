"""
Custom exceptions for the cli service.
"""


class InvalidInputError(Exception):
    """Raised when input data is invalid or in an incorrect format."""

    pass


class DirectoryCreationError(Exception):
    """Raised when there's an error creating required directories."""

    pass


class EncryptionKeyError(Exception):
    """Raised when there's an error with encryption key generation or loading."""

    pass


class LimitExceededError(Exception):
    """Raised when there's an limit exceeded error in alarm creation."""

    pass


class ValidationError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class AccountIdError(Exception):
    """Unable to retrieve account ID"""

    def __init__(
        self,
        message: str = "Unable to confirm Account ID. Credentials might be missing.",
    ):
        super().__init__(message)


class MalformedResponseError(Exception):
    """Raised when API response data is malformed or missing required fields."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class MissingInputFieldError(Exception):
    """Raised when input data is missing a required field."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class SupportCaseAlreadyExistsError(Exception):
    """Raised when a support case with the same subject already exists"""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class MloAdapterTypeError(Exception):
    """Raised when Mlo Adaptor is called to transform an incompatible type"""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class AlarmIngestionValidationError(Exception):
    """Raised when alarm ingestion data is invalid"""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class AlarmCreationValidationError(Exception):
    """Raised when alarm creation data is invalid"""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class SupportCaseNotFoundError(Exception):
    """Raised when a support case is not found"""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)
