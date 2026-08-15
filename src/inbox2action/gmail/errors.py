"""Safe error taxonomy for the Gmail readonly boundary."""

from __future__ import annotations


class GmailError(Exception):
    """Base class whose string value is always a safe, non-secret code."""

    code = "gmail_error"

    def __init__(self) -> None:
        super().__init__(self.code)


class GmailOAuthError(GmailError):
    """Base class for local OAuth and token failures."""


class GmailOAuthClientNotFoundError(GmailOAuthError):
    """The configured OAuth client JSON does not exist."""

    code = "oauth_client_not_found"


class GmailOAuthClientConfigError(GmailOAuthError):
    """The OAuth client JSON cannot be used as a desktop-app config."""

    code = "oauth_client_config_invalid"


class GmailAuthorizationDeniedError(GmailOAuthError):
    """The user declined the requested readonly permission."""

    code = "oauth_authorization_denied"


class GmailOAuthCallbackError(GmailOAuthError):
    """The localhost OAuth callback did not complete successfully."""

    code = "oauth_callback_failed"


class GmailTokenInvalidError(GmailOAuthError):
    """The persisted token is missing, malformed, or has an invalid scope."""

    code = "token_invalid"


class GmailTokenRefreshError(GmailOAuthError):
    """The persisted token could not be refreshed."""

    code = "token_refresh_failed"


class GmailTokenPersistenceError(GmailOAuthError):
    """The token could not be written to its external location."""

    code = "token_persistence_failed"


class GmailTransportError(GmailError):
    """Base class for Gmail API transport failures."""


class GmailApiNetworkError(GmailTransportError):
    """The Gmail API could not be reached or returned a transient failure."""

    code = "gmail_api_network_error"


class GmailApiAuthenticationError(GmailTransportError):
    """The Gmail API rejected the access-token authentication."""

    code = "gmail_api_authentication_error"


class GmailApiAuthorizationError(GmailTransportError):
    """The Gmail API rejected the requested readonly operation."""

    code = "gmail_api_authorization_error"


class GmailApiResponseError(GmailTransportError):
    """The Gmail API returned an unexpected non-transient response."""

    code = "gmail_api_response_error"
