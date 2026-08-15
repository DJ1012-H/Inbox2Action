from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

import pytest

import inbox2action.gmail.oauth as gmail_oauth
from inbox2action.gmail import (
    GMAIL_READONLY_SCOPE,
    GmailAuthorizationDeniedError,
    GmailOAuthCallbackError,
    GmailOAuthClientConfigError,
    GmailOAuthClientNotFoundError,
    GmailOAuthConfig,
    GmailOAuthCredentialProvider,
    GmailTokenInvalidError,
    GmailTokenPersistenceError,
    GmailTokenRefreshError,
)


@pytest.fixture(autouse=True)
def _use_test_token_permissions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        gmail_oauth,
        "_harden_secret_permissions",
        lambda path: path.chmod(0o600),
    )


class FakeCredentials:
    def __init__(
        self,
        *,
        valid: bool,
        expired: bool = False,
        refresh_token: str | None = None,
        scopes: list[str] | None = None,
    ) -> None:
        self.valid = valid
        self.expired = expired
        self.refresh_token = refresh_token
        self.scopes = scopes
        self.refresh_calls = 0

    def refresh(self, request: object) -> None:
        del request
        self.refresh_calls += 1
        self.valid = True
        self.expired = False

    def to_json(self) -> str:
        return json.dumps(
            {
                "token": "ACCESS_TOKEN_SHOULD_NEVER_BE_LOGGED",
                "refresh_token": "REFRESH_TOKEN_SHOULD_NEVER_BE_LOGGED",
                "scopes": [GMAIL_READONLY_SCOPE],
            }
        )


def _client_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "installed": {
                    "client_id": "client-id",
                    "client_secret": "CLIENT_SECRET_SHOULD_NEVER_BE_LOGGED",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": ["http://localhost"],
                }
            }
        ),
        encoding="utf-8",
    )


def _config(tmp_path: Path) -> GmailOAuthConfig:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    secrets = tmp_path / "external" / "gmail-oauth-client.json"
    token = tmp_path / "external" / "gmail-token.json"
    secrets.parent.mkdir()
    _client_config(secrets)
    return GmailOAuthConfig(secrets, token, project_root)


def test_first_authorization_uses_only_fixed_readonly_scope_and_hides_secrets(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    config = _config(tmp_path)
    captured: dict[str, object] = {}
    credentials = FakeCredentials(valid=True, scopes=[GMAIL_READONLY_SCOPE])

    class FakeFlow:
        def run_local_server(self, **kwargs: object) -> FakeCredentials:
            captured["run_kwargs"] = kwargs
            return credentials

    def flow_factory(client_config: dict[str, object], scopes: list[str]) -> FakeFlow:
        captured["scopes"] = scopes
        assert client_config["installed"]
        return FakeFlow()

    caplog.set_level(logging.INFO)
    provider = GmailOAuthCredentialProvider(config, flow_factory=flow_factory)
    assert provider() is credentials

    assert captured["scopes"] == [GMAIL_READONLY_SCOPE]
    assert captured["run_kwargs"] == {
        "port": 0,
        "open_browser": True,
        "access_type": "offline",
        "prompt": "consent",
    }
    assert config.token_path.exists()
    assert "ACCESS_TOKEN_SHOULD_NEVER_BE_LOGGED" not in caplog.text
    assert "REFRESH_TOKEN_SHOULD_NEVER_BE_LOGGED" not in caplog.text
    assert "CLIENT_SECRET_SHOULD_NEVER_BE_LOGGED" not in caplog.text


def test_extra_scope_is_rejected_without_fallback(tmp_path: Path) -> None:
    config = _config(tmp_path)
    credentials = FakeCredentials(
        valid=True,
        scopes=[GMAIL_READONLY_SCOPE, "https://www.googleapis.com/auth/gmail.modify"],
    )
    provider = GmailOAuthCredentialProvider(
        config,
        flow_factory=lambda _config, _scopes: _FakeFlow(credentials),
    )

    with pytest.raises(GmailTokenInvalidError):
        provider()
    assert not config.token_path.exists()


class _FakeFlow:
    def __init__(self, credentials: FakeCredentials | Exception) -> None:
        self.credentials = credentials

    def run_local_server(self, **kwargs: object) -> FakeCredentials:
        del kwargs
        if isinstance(self.credentials, Exception):
            raise self.credentials
        return self.credentials


def test_missing_client_json_is_distinguished(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    config = GmailOAuthConfig(
        tmp_path / "external" / "missing.json",
        tmp_path / "external" / "token.json",
        project_root,
    )
    provider = GmailOAuthCredentialProvider(config)

    with pytest.raises(GmailOAuthClientNotFoundError):
        provider()


def test_illegal_client_json_is_distinguished(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.client_secrets_path.write_text("not-json", encoding="utf-8")

    with pytest.raises(GmailOAuthClientConfigError):
        GmailOAuthCredentialProvider(config)()


def test_existing_valid_token_does_not_start_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    config.token_path.parent.mkdir(exist_ok=True)
    config.token_path.write_text(
        json.dumps({"scopes": [GMAIL_READONLY_SCOPE]}), encoding="utf-8"
    )
    credentials = FakeCredentials(valid=True, scopes=[GMAIL_READONLY_SCOPE])

    def fail_flow(_config: dict[str, object], _scopes: list[str]) -> object:
        raise AssertionError("browser flow must not run for a valid token")

    hardened_paths: list[Path] = []
    monkeypatch.setattr(
        gmail_oauth,
        "_harden_secret_permissions",
        lambda path: hardened_paths.append(path),
    )

    provider = GmailOAuthCredentialProvider(
        config,
        flow_factory=fail_flow,
        credentials_loader=lambda _info, _scopes: credentials,
    )
    assert provider() is credentials
    assert hardened_paths == [config.token_path]


def test_permission_hardening_failure_preserves_existing_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    config.token_path.parent.mkdir(exist_ok=True)
    config.token_path.write_text("existing-token", encoding="utf-8")
    provider = GmailOAuthCredentialProvider(config)

    def fail_hardening(_path: Path) -> None:
        raise OSError

    monkeypatch.setattr(gmail_oauth, "_harden_secret_permissions", fail_hardening)
    with pytest.raises(GmailTokenPersistenceError):
        provider._persist(FakeCredentials(valid=True, scopes=[GMAIL_READONLY_SCOPE]))

    assert config.token_path.read_text(encoding="utf-8") == "existing-token"
    assert list(config.token_path.parent.glob(".gmail-token.json.*.tmp")) == []


def test_windows_acl_removes_inheritance_and_uses_stable_sids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []
    user_sid = "S-1-5-21-100-200-300-1001"

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[0] == "whoami":
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=f'"DOMAIN\\user","{user_sid}"\n',
                stderr="",
            )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(gmail_oauth.subprocess, "run", fake_run)
    token_path = tmp_path / "gmail-token.json"
    gmail_oauth._harden_windows_acl(token_path)

    assert calls[0] == ["whoami", "/user", "/fo", "csv", "/nh"]
    assert calls[1] == [
        "icacls",
        str(token_path),
        "/inheritance:r",
        "/grant:r",
        f"*{user_sid}:(F)",
        "*S-1-5-18:(F)",
        "*S-1-5-32-544:(F)",
    ]


def test_expired_token_refreshes_and_persists(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.token_path.parent.mkdir(exist_ok=True)
    config.token_path.write_text(
        json.dumps({"scopes": [GMAIL_READONLY_SCOPE]}), encoding="utf-8"
    )
    credentials = FakeCredentials(
        valid=False,
        expired=True,
        refresh_token="REFRESH_TOKEN_SHOULD_NEVER_BE_LOGGED",
        scopes=[GMAIL_READONLY_SCOPE],
    )
    requested = object()
    provider = GmailOAuthCredentialProvider(
        config,
        credentials_loader=lambda _info, _scopes: credentials,
        request_factory=lambda: requested,
    )

    assert provider() is credentials
    assert credentials.refresh_calls == 1
    assert config.token_path.exists()


def test_refresh_failure_does_not_fallback_to_browser(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.token_path.parent.mkdir(exist_ok=True)
    config.token_path.write_text(
        json.dumps({"scopes": [GMAIL_READONLY_SCOPE]}), encoding="utf-8"
    )

    class RefreshFails(FakeCredentials):
        def refresh(self, request: object) -> None:
            del request
            raise RuntimeError("refresh failed")

    credentials = RefreshFails(
        valid=False,
        expired=True,
        refresh_token="refresh-token",
        scopes=[GMAIL_READONLY_SCOPE],
    )
    provider = GmailOAuthCredentialProvider(
        config,
        credentials_loader=lambda _info, _scopes: credentials,
        flow_factory=lambda _config, _scopes: pytest.fail("must not reauthorize"),
    )

    with pytest.raises(GmailTokenRefreshError):
        provider()


def test_denied_authorization_and_callback_failures_are_distinct(tmp_path: Path) -> None:
    config = _config(tmp_path)

    class AccessDenied(Exception):
        error = "access_denied"

    denied = GmailOAuthCredentialProvider(
        config,
        flow_factory=lambda _config, _scopes: _FakeFlow(AccessDenied()),
    )
    with pytest.raises(GmailAuthorizationDeniedError):
        denied()

    callback = GmailOAuthCredentialProvider(
        config,
        flow_factory=lambda _config, _scopes: _FakeFlow(RuntimeError()),
    )
    with pytest.raises(GmailOAuthCallbackError):
        callback()


def test_secret_paths_inside_repository_are_rejected(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    with pytest.raises(GmailOAuthClientConfigError):
        GmailOAuthConfig(
            project_root / "gmail-oauth-client.json",
            tmp_path / "external" / "gmail-token.json",
            project_root,
        )
