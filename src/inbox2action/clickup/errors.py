"""Safe error taxonomy for the ClickUp readonly boundary."""

from __future__ import annotations


class ClickUpError(Exception):
    """Base class whose string value is always a safe, stable error code."""

    code = "clickup_error"

    def __init__(self) -> None:
        super().__init__(self.code)


class ClickUpConfigurationError(ClickUpError):
    """The local ClickUp configuration is missing or invalid."""

    code = "configuration"


class ClickUpAuthenticationError(ClickUpError):
    """ClickUp rejected the token."""

    code = "authentication"


class ClickUpForbiddenError(ClickUpError):
    """ClickUp rejected access to the requested readonly resource."""

    code = "forbidden"


class ClickUpNotFoundError(ClickUpError):
    """ClickUp could not find the requested resource."""

    code = "not_found"


class ClickUpRateLimitedError(ClickUpError):
    """ClickUp rate-limited the readonly request."""

    code = "rate_limited"


class ClickUpTimeoutError(ClickUpError):
    """The readonly request exceeded its configured timeout."""

    code = "timeout"


class ClickUpUnavailableError(ClickUpError):
    """ClickUp or the network was temporarily unavailable."""

    code = "unavailable"


class ClickUpInvalidResponseError(ClickUpError):
    """ClickUp returned invalid JSON or an unexpected response shape."""

    code = "invalid_response"


class ClickUpInvalidRequestError(ClickUpInvalidResponseError):
    """ClickUp rejected a deterministic request validation failure."""

    code = "invalid_request"
