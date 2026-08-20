"""Serve the existing HITL approval UI with the Stage 8 Calendar executor."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence

from inbox2action.calendar import GoogleCalendarWriteExecutor
from inbox2action.calendar.client import GoogleCalendarClient
from inbox2action.config import Settings
from inbox2action.gmail import GmailOAuthConfig, GoogleOAuthCredentialProvider
from inbox2action.stage3 import FixtureWriteExecutor, build_email_action_graph
from inbox2action.stage4 import open_langgraph_postgres, upgrade_database
from inbox2action.stage6 import ApprovalService, PostgresWorkflowIndex
from inbox2action.stage6.server import serve_approval_ui


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Serve the existing Stage 6 HITL page for Google Calendar proposals."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument(
        "--skip-migrations",
        action="store_true",
        help="Do not run Alembic; use the dedicated migration service in Compose.",
    )
    return parser


async def run_server(args: argparse.Namespace) -> int:
    settings = Settings()
    database_url = settings.database_url_value
    if not database_url:
        raise SystemExit("INBOX2ACTION_DATABASE_URL must be configured")
    if not args.skip_migrations:
        upgrade_database(database_url)
    if settings.google_calendar_enabled:
        if settings.google_calendar_id is None:
            raise SystemExit("GOOGLE_CALENDAR_ID must be configured")
        credentials = GoogleOAuthCredentialProvider(
            GmailOAuthConfig(
                client_secrets_path=settings.gmail_client_secrets_path
                or GmailOAuthConfig().client_secrets_path,
                token_path=settings.gmail_token_path or GmailOAuthConfig().token_path,
            )
        )
        client = GoogleCalendarClient.from_credentials_provider(credentials)
        executor = GoogleCalendarWriteExecutor(
            client,
            calendar_id=settings.google_calendar_id,
            timezone=settings.business_timezone,
            enabled=True,
        )
    else:
        executor = FixtureWriteExecutor()
    index = PostgresWorkflowIndex(database_url)
    try:
        async with open_langgraph_postgres(database_url) as postgres:
            graph = build_email_action_graph(
                checkpointer=postgres.checkpointer,
                store=postgres.store,
                execution_ledger=postgres.execution_ledger,
                write_executor=executor,
            )
            await serve_approval_ui(
                ApprovalService(graph, index), host=args.host, port=args.port
            )
    finally:
        await index.close()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not 1 <= args.port <= 65535:
        raise SystemExit("--port must be between 1 and 65535")
    return asyncio.run(
        run_server(args),
        loop_factory=asyncio.SelectorEventLoop,
    )


if __name__ == "__main__":
    raise SystemExit(main())
