class PlanningError(Exception):
    """Base error for planning failures."""


class ClarificationRequired(PlanningError):
    """Raised when the request needs more user input."""


class ProviderUnavailableError(PlanningError):
    """Raised when a third-party provider is not configured or unavailable."""


class ProviderRequestError(PlanningError):
    """Raised when a third-party provider request fails."""
