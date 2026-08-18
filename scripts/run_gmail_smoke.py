"""Opt-in local Gmail readonly OAuth and transport smoke test."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from inbox2action.config import Settings, resolve_configured_path
from inbox2action.gmail import (
    PILOT_MAX_MESSAGES,
    GmailError,
    GmailOAuthConfig,
    GmailOAuthCredentialProvider,
    GmailReadonlyTransport,
)


def _message_count(value: str) -> int:
    try:
        count = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("max-messages must be an integer") from exc
    if not 1 <= count <= PILOT_MAX_MESSAGES:
        raise argparse.ArgumentTypeError(
            f"max-messages must be between 1 and {PILOT_MAX_MESSAGES}"
        )
    return count


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Authorize Gmail readonly access and print bounded message metadata."
    )
    parser.add_argument(
        "--client-secrets",
        type=Path,
        default=None,
        help="External Desktop OAuth client JSON path.",
    )
    parser.add_argument(
        "--token-path",
        type=Path,
        default=None,
        help="External OAuth token path.",
    )
    parser.add_argument(
        "--max-messages",
        type=_message_count,
        default=10,
        help="Maximum metadata summaries to print (1-20).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = Settings()
        config = GmailOAuthConfig(
            client_secrets_path=resolve_configured_path(
                args.client_secrets,
                settings.gmail_client_secrets_path,
                setting_name="GMAIL_CLIENT_SECRETS_PATH or --client-secrets",
            ),
            token_path=resolve_configured_path(
                args.token_path,
                settings.gmail_token_path,
                setting_name="GMAIL_TOKEN_PATH or --token-path",
            ),
        )
        credentials = GmailOAuthCredentialProvider(config)
        transport = GmailReadonlyTransport(credentials)
        profile = transport.get_profile()
        messages = transport.read_recent_messages(args.max_messages)
    except ValueError as error:
        print(f"gmail_smoke_failed: configuration ({error})", file=sys.stderr)
        return 1
    except GmailError as error:
        print(f"gmail_smoke_failed: {error.code}", file=sys.stderr)
        return 1

    print(f"profile email: {profile.email_address}")
    print(f"message count: {len(messages)}")
    for message in messages:
        print(f"message id: {message.message_id}")
        print(f"thread id: {message.thread_id}")
        print(f"From: {message.from_address}")
        print(f"Subject: {message.subject}")
        print(f"Date: {message.date}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
