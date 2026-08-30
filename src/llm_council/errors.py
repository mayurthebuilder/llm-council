"""Safe, user-facing error types for council operations."""


class CouncilError(Exception):
    """Base class for concise errors that are safe to show to users."""


class InputError(CouncilError):
    """Raised when explicitly supplied input is invalid or unsafe."""


class ProviderError(CouncilError):
    """Raised when a configured model provider cannot complete a request."""


class QuorumError(CouncilError):
    """Raised when too few advisor or peer-review results are available."""


class OutputError(CouncilError):
    """Raised when a requested output destination is invalid or unsafe."""
