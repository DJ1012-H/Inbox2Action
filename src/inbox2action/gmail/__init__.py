"""Gmail readonly OAuth transport for the Inbox2Action pilot."""

from .errors import (
    GmailApiAuthenticationError,
    GmailApiAuthorizationError,
    GmailApiNetworkError,
    GmailApiResponseError,
    GmailAuthorizationDeniedError,
    GmailError,
    GmailOAuthCallbackError,
    GmailOAuthClientConfigError,
    GmailOAuthClientNotFoundError,
    GmailTokenInvalidError,
    GmailTokenPersistenceError,
    GmailTokenRefreshError,
)
from .oauth import (
    DEFAULT_CLIENT_SECRETS_PATH,
    DEFAULT_TOKEN_PATH,
    GMAIL_READONLY_SCOPE,
    GmailOAuthConfig,
    GmailOAuthCredentialProvider,
)
from .readonly import (
    PILOT_MAX_MESSAGES,
    PILOT_MAX_PAGES,
    PILOT_PAGE_SIZE,
    PILOT_QUERY,
    GmailMessageSummary,
    GmailProfile,
    GmailReadonlyTransport,
)

__all__ = [
    "DEFAULT_CLIENT_SECRETS_PATH",
    "DEFAULT_TOKEN_PATH",
    "GMAIL_READONLY_SCOPE",
    "PILOT_MAX_MESSAGES",
    "PILOT_MAX_PAGES",
    "PILOT_PAGE_SIZE",
    "PILOT_QUERY",
    "GmailApiAuthenticationError",
    "GmailApiAuthorizationError",
    "GmailApiNetworkError",
    "GmailApiResponseError",
    "GmailAuthorizationDeniedError",
    "GmailError",
    "GmailMessageSummary",
    "GmailOAuthCallbackError",
    "GmailOAuthClientConfigError",
    "GmailOAuthClientNotFoundError",
    "GmailOAuthConfig",
    "GmailOAuthCredentialProvider",
    "GmailProfile",
    "GmailReadonlyTransport",
    "GmailTokenInvalidError",
    "GmailTokenPersistenceError",
    "GmailTokenRefreshError",
]
