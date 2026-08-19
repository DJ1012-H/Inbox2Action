"""Local desktop OAuth and external token persistence for Gmail readonly access."""

from __future__ import annotations

import csv
import json
import logging
import os
import re
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import (
    GmailAuthorizationDeniedError,
    GmailOAuthCallbackError,
    GmailOAuthClientConfigError,
    GmailOAuthClientNotFoundError,
    GmailTokenInvalidError,
    GmailTokenPersistenceError,
    GmailTokenRefreshError,
)

logger = logging.getLogger(__name__)

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GOOGLE_CALENDAR_FREEBUSY_SCOPE = (
    "https://www.googleapis.com/auth/calendar.freebusy"
)
GOOGLE_CALENDAR_EVENTS_OWNED_SCOPE = (
    "https://www.googleapis.com/auth/calendar.events.owned"
)
GOOGLE_CALENDAR_SCOPES = (
    GOOGLE_CALENDAR_FREEBUSY_SCOPE,
    GOOGLE_CALENDAR_EVENTS_OWNED_SCOPE,
)
GOOGLE_REQUIRED_SCOPES = (GMAIL_READONLY_SCOPE, *GOOGLE_CALENDAR_SCOPES)


def _local_appdata() -> Path:
    configured = os.environ.get("LOCALAPPDATA")
    if configured:
        return Path(configured)
    return Path.home() / "AppData" / "Local"


DEFAULT_SECRET_DIRECTORY = _local_appdata() / "Inbox2Action" / "secrets"
DEFAULT_CLIENT_SECRETS_PATH = DEFAULT_SECRET_DIRECTORY / "gmail-oauth-client.json"
DEFAULT_TOKEN_PATH = DEFAULT_SECRET_DIRECTORY / "gmail-token.json"
DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_EXPECTED_SCOPES = frozenset({GMAIL_READONLY_SCOPE})
_ALLOWED_SCOPES = frozenset(GOOGLE_REQUIRED_SCOPES)
_WINDOWS_SYSTEM_SID = "S-1-5-18"
_WINDOWS_ADMINISTRATORS_SID = "S-1-5-32-544"
_WINDOWS_SID_PATTERN = re.compile(r"S-\d+(?:-\d+)+", re.IGNORECASE)


@dataclass(frozen=True)
class GmailOAuthConfig:
    """External paths used by the Gmail OAuth boundary.

    Both files are required to live outside the repository. The client JSON is
    only read when a new authorization is needed; a valid token can be reused
    without it.
    """

    client_secrets_path: Path = DEFAULT_CLIENT_SECRETS_PATH
    token_path: Path = DEFAULT_TOKEN_PATH
    project_root: Path = DEFAULT_PROJECT_ROOT

    def __post_init__(self) -> None:
        client_path = Path(self.client_secrets_path).expanduser().resolve()
        token_path = Path(self.token_path).expanduser().resolve()
        project_root = Path(self.project_root).expanduser().resolve()
        if _is_within(client_path, project_root) or _is_within(token_path, project_root):
            raise GmailOAuthClientConfigError()
        if client_path == token_path:
            raise GmailOAuthClientConfigError()
        object.__setattr__(self, "client_secrets_path", client_path)
        object.__setattr__(self, "token_path", token_path)
        object.__setattr__(self, "project_root", project_root)


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _normalise_scopes(value: Any) -> frozenset[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return frozenset({value})
    if isinstance(value, (list, tuple, set, frozenset)) and all(
        isinstance(scope, str) for scope in value
    ):
        return frozenset(value)
    raise ValueError


class GmailOAuthCredentialProvider:
    """Load, refresh, or obtain Google credentials with an allowlisted scope set."""

    def __init__(
        self,
        config: GmailOAuthConfig | None = None,
        *,
        flow_factory: Callable[[dict[str, Any], list[str]], Any] | None = None,
        credentials_loader: Callable[[dict[str, Any], list[str]], Any] | None = None,
        request_factory: Callable[[], Any] | None = None,
        scopes: tuple[str, ...] = (GMAIL_READONLY_SCOPE,),
    ) -> None:
        requested_scopes = tuple(dict.fromkeys(scopes))
        if not requested_scopes or not set(requested_scopes).issubset(_ALLOWED_SCOPES):
            raise GmailOAuthClientConfigError()
        self.config = config or GmailOAuthConfig()
        self._flow_factory = flow_factory or _default_flow_factory
        self._credentials_loader = credentials_loader or _default_credentials_loader
        self._request_factory = request_factory or _default_request_factory
        self._scopes = requested_scopes
        self._required_scopes = frozenset(requested_scopes)

    def __call__(self) -> Any:
        return self.get_credentials()

    def get_credentials(self, *, force_reauthorize: bool = False) -> Any:
        if force_reauthorize:
            credentials = self._authorize()
            _validate_credential_scopes(credentials, self._required_scopes)
            self._persist(credentials)
            logger.info("google_oauth_reauthorization_completed")
            return credentials
        if self.config.token_path.exists():
            self._harden_existing_token()
            credentials = self._load_persisted_token()
            if getattr(credentials, "valid", False):
                _validate_credential_scopes(credentials, self._required_scopes)
                logger.info("google_oauth_token_loaded")
                return credentials
            if not getattr(credentials, "expired", False) or not getattr(
                credentials, "refresh_token", None
            ):
                raise GmailTokenInvalidError()
            return self._refresh(credentials)

        credentials = self._authorize()
        _validate_credential_scopes(credentials, self._required_scopes)
        self._persist(credentials)
        logger.info("google_oauth_authorization_completed")
        return credentials

    def reauthorize(self) -> Any:
        """Run the local browser flow and atomically replace the external token."""

        return self.get_credentials(force_reauthorize=True)

    def _harden_existing_token(self) -> None:
        try:
            _harden_secret_permissions(self.config.token_path)
        except OSError:
            raise GmailTokenPersistenceError() from None

    def _load_persisted_token(self) -> Any:
        try:
            token_info = json.loads(self.config.token_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise GmailTokenInvalidError() from None
        if not isinstance(token_info, dict):
            raise GmailTokenInvalidError()
        try:
            token_scopes = _normalise_scopes(token_info.get("scopes"))
            if token_scopes is not None and not _scopes_are_allowed(
                token_scopes, self._required_scopes
            ):
                raise GmailTokenInvalidError()
            credentials = self._credentials_loader(token_info, list(self._scopes))
            _validate_credential_scopes(credentials, self._required_scopes)
            return credentials
        except GmailTokenInvalidError:
            raise
        except Exception:  # noqa: BLE001 - provider errors become a safe token code
            raise GmailTokenInvalidError() from None

    def _refresh(self, credentials: Any) -> Any:
        try:
            credentials.refresh(self._request_factory())
            _validate_credential_scopes(credentials, self._required_scopes)
            self._persist(credentials)
        except GmailTokenPersistenceError:
            raise
        except GmailTokenInvalidError:
            raise
        except Exception:  # noqa: BLE001 - refresh errors become a safe token code
            raise GmailTokenRefreshError() from None
        logger.info("gmail_oauth_token_refreshed")
        return credentials

    def _authorize(self) -> Any:
        client_config = self._load_client_config()
        try:
            flow = self._flow_factory(client_config, list(self._scopes))
        except GmailOAuthClientConfigError:
            raise
        except Exception:  # noqa: BLE001 - config construction errors stay classified
            raise GmailOAuthClientConfigError() from None
        try:
            return flow.run_local_server(
                port=0,
                open_browser=True,
                access_type="offline",
                prompt="consent",
            )
        except Exception as exc:  # noqa: BLE001 - callback errors are classified below
            if _is_authorization_denied(exc):
                raise GmailAuthorizationDeniedError() from None
            raise GmailOAuthCallbackError() from None

    def _load_client_config(self) -> dict[str, Any]:
        path = self.config.client_secrets_path
        if not path.exists():
            raise GmailOAuthClientNotFoundError()
        try:
            content = path.read_text(encoding="utf-8")
            config = json.loads(content)
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise GmailOAuthClientConfigError() from None
        if not _is_desktop_client_config(config):
            raise GmailOAuthClientConfigError()
        return config

    def _persist(self, credentials: Any) -> None:
        try:
            payload = credentials.to_json()
            if not isinstance(payload, str):
                raise TypeError
            self.config.token_path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary_name = tempfile.mkstemp(
                prefix=f".{self.config.token_path.name}.",
                suffix=".tmp",
                dir=self.config.token_path.parent,
                text=True,
            )
            temporary_path = Path(temporary_name)
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                _harden_secret_permissions(temporary_path)
                os.replace(temporary_path, self.config.token_path)
            finally:
                if temporary_path.exists():
                    temporary_path.unlink()
        except GmailTokenPersistenceError:
            raise
        except (OSError, ValueError, TypeError):
            raise GmailTokenPersistenceError() from None


def _harden_secret_permissions(path: Path) -> None:
    path.chmod(0o600)
    if os.name == "nt":
        _harden_windows_acl(path)


def _harden_windows_acl(path: Path) -> None:
    user_sid = _current_windows_user_sid()
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(
        [
            "icacls",
            str(path),
            "/inheritance:r",
            "/grant:r",
            f"*{user_sid}:(F)",
            f"*{_WINDOWS_SYSTEM_SID}:(F)",
            f"*{_WINDOWS_ADMINISTRATORS_SID}:(F)",
        ],
        check=False,
        capture_output=True,
        text=True,
        creationflags=creationflags,
    )
    if result.returncode != 0:
        raise OSError("unable to harden Windows secret ACL")


def _current_windows_user_sid() -> str:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(
        ["whoami", "/user", "/fo", "csv", "/nh"],
        check=False,
        capture_output=True,
        text=True,
        creationflags=creationflags,
    )
    if result.returncode != 0:
        raise OSError("unable to resolve current Windows user SID")
    try:
        row = next(csv.reader(result.stdout.splitlines()))
    except (StopIteration, csv.Error):
        raise OSError("unable to parse current Windows user SID") from None
    if len(row) < 2:
        raise OSError("unable to parse current Windows user SID")
    sid = row[-1].strip()
    if _WINDOWS_SID_PATTERN.fullmatch(sid) is None:
        raise OSError("invalid current Windows user SID")
    return sid


def _is_desktop_client_config(config: Any) -> bool:
    if not isinstance(config, dict) or set(config) != {"installed"}:
        return False
    installed = config.get("installed")
    if not isinstance(installed, dict):
        return False
    required = ("client_id", "client_secret", "auth_uri", "token_uri")
    if any(not isinstance(installed.get(key), str) or not installed[key] for key in required):
        return False
    redirect_uris = installed.get("redirect_uris")
    return isinstance(redirect_uris, list) and all(
        isinstance(uri, str) and uri for uri in redirect_uris
    )


def _scopes_are_allowed(
    scopes: frozenset[str], required_scopes: frozenset[str]
) -> bool:
    return required_scopes.issubset(scopes) and scopes.issubset(_ALLOWED_SCOPES)


def _validate_credential_scopes(
    credentials: Any,
    required_scopes: frozenset[str] = _EXPECTED_SCOPES,
) -> None:
    saw_scope_metadata = False
    for attribute in ("scopes", "granted_scopes"):
        try:
            value = getattr(credentials, attribute, None)
            normalised = _normalise_scopes(value)
        except (AttributeError, ValueError, TypeError):
            raise GmailTokenInvalidError() from None
        if normalised is None:
            continue
        saw_scope_metadata = True
        if not _scopes_are_allowed(normalised, required_scopes):
            raise GmailTokenInvalidError()
    if not saw_scope_metadata:
        raise GmailTokenInvalidError()


def _is_authorization_denied(error: Exception) -> bool:
    error_code = getattr(error, "error", None)
    if error_code == "access_denied":
        return True
    return type(error).__name__ in {
        "AccessDenied",
        "AccessDeniedError",
        "AuthorizationDeniedError",
    }


def _default_flow_factory(client_config: dict[str, Any], scopes: list[str]) -> Any:
    from google_auth_oauthlib.flow import (  # type: ignore[import-not-found]
        InstalledAppFlow,
    )

    return InstalledAppFlow.from_client_config(client_config, scopes=scopes)


def _default_credentials_loader(token_info: dict[str, Any], scopes: list[str]) -> Any:
    from google.oauth2.credentials import Credentials  # type: ignore[import-not-found]

    return Credentials.from_authorized_user_info(token_info, scopes=scopes)


def _default_request_factory() -> Any:
    from google.auth.transport.requests import Request  # type: ignore[import-not-found]

    return Request()


class GoogleOAuthCredentialProvider(GmailOAuthCredentialProvider):
    """Shared Stage 5 token architecture with the narrow Stage 8 scopes."""

    def __init__(
        self,
        config: GmailOAuthConfig | None = None,
        *,
        flow_factory: Callable[[dict[str, Any], list[str]], Any] | None = None,
        credentials_loader: Callable[[dict[str, Any], list[str]], Any] | None = None,
        request_factory: Callable[[], Any] | None = None,
    ) -> None:
        super().__init__(
            config,
            flow_factory=flow_factory,
            credentials_loader=credentials_loader,
            request_factory=request_factory,
            scopes=GOOGLE_REQUIRED_SCOPES,
        )
