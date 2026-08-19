"""Explicitly reauthorize the shared Stage 5 Google token for Stage 8 scopes."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from inbox2action.config import Settings, resolve_configured_path
from inbox2action.gmail import (
    DEFAULT_CLIENT_SECRETS_PATH,
    DEFAULT_TOKEN_PATH,
    GOOGLE_REQUIRED_SCOPES,
    GmailOAuthConfig,
    GoogleOAuthCredentialProvider,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Authorize the existing Google Desktop OAuth client for Stage 5 + Stage 8 narrow scopes."
    )
    parser.add_argument("--client-secrets", type=Path, default=None)
    parser.add_argument("--token-path", type=Path, default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings()
    config = GmailOAuthConfig(
        client_secrets_path=resolve_configured_path(
            args.client_secrets,
            settings.gmail_client_secrets_path or DEFAULT_CLIENT_SECRETS_PATH,
            setting_name="GMAIL_CLIENT_SECRETS_PATH or --client-secrets",
        ),
        token_path=resolve_configured_path(
            args.token_path,
            settings.gmail_token_path or DEFAULT_TOKEN_PATH,
            setting_name="GMAIL_TOKEN_PATH or --token-path",
        ),
    )
    provider = GoogleOAuthCredentialProvider(config)
    provider.reauthorize()
    print("google_oauth_reauthorization_succeeded")
    print(f"scope_count: {len(GOOGLE_REQUIRED_SCOPES)}")
    print("token_path: external configured path")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
