class PrismaxError(Exception):
    """Base SDK error."""


class PrismaxAuthError(PrismaxError):
    """Raised when an API key is missing or rejected."""


class PrismaxValidationError(PrismaxError):
    """Raised when local upload input is invalid."""


class PrismaxApiError(PrismaxError):
    """Raised when the PrismaX API returns an error."""
