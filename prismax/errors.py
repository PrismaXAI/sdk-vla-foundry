class PrismaxError(Exception):
    """Base SDK error."""

    def __init__(self, message, *, details=None):
        super().__init__(message)
        self.details = details or {}


class PrismaxAuthError(PrismaxError):
    """Raised when an API key is missing or rejected."""


class PrismaxValidationError(PrismaxError):
    """Raised when local upload input is invalid."""


class PrismaxApiError(PrismaxError):
    """Raised when the PrismaX API returns an error."""
