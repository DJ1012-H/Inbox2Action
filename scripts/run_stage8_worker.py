"""Run one bounded Gmail -> Calendar Stage 8 worker pass."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from pathlib import Path

from inbox2action.calendar import (
    CalendarToolRuntime,
    GoogleCalendarClient,
    GoogleCalendarFreeBusyAdapter,
    GoogleCalendarWriteExecutor,
)
from inbox2action.config import Settings, resolve_configured_path
from inbox2action.gmail import (
    DEFAULT_CLIENT_SECRETS_PATH,
    DEFAULT_TOKEN_PATH,
    GmailOAuthConfig,
    GmailReadonlyTransport,
    GoogleOAuthCredentialProvider,
)
from inbox2action.llm import OpenAIChatClient
from inbox2action.memory import MemoryService
from inbox2action.stage3 import build_email_action_graph
from inbox2action.stage4 import open_langgraph_postgres, upgrade_database
from inbox2action.stage6 import GmailWorkflowWorker, PostgresWorkflowIndex
from inbox2action.stage8 import CalendarStage8Planner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Poll bounded Gmail and pause at the existing HITL before Google Calendar writes."
    )
    parser.add_argument("--client-secrets", type=Path, default=None)
    parser.add_argument("--token-path", type=Path, default=None)
    parser.add_argument("--max-messages", type=int, default=10)
    return parser


async def run_once(args: argparse.Namespace) -> int:
    settings = Settings()
    database_url = settings.database_url_value
    if not database_url:
        raise SystemExit("INBOX2ACTION_DATABASE_URL must be configured")
    if settings.google_calendar_id is None:
        raise SystemExit("GOOGLE_CALENDAR_ID must be configured")
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
    credentials = GoogleOAuthCredentialProvider(config)
    client = GoogleCalendarClient.from_credentials_provider(credentials)
    adapter = GoogleCalendarFreeBusyAdapter(
        client,
        calendar_id=settings.google_calendar_id,
        timezone=settings.business_timezone,
    )
    runtime = CalendarToolRuntime(adapter, timezone=settings.business_timezone)
    executor = GoogleCalendarWriteExecutor(
        client,
        calendar_id=settings.google_calendar_id,
        timezone=settings.business_timezone,
        enabled=settings.google_calendar_enabled,
    )
    upgrade_database(database_url)
    index = PostgresWorkflowIndex(database_url)
    try:
        transport = GmailReadonlyTransport(credentials)
        async with open_langgraph_postgres(database_url) as postgres:
            planner = CalendarStage8Planner(
                OpenAIChatClient(settings),
                runtime,
                timezone=settings.business_timezone,
                max_tool_steps=settings.llm_max_tool_steps,
                memory_service=MemoryService(postgres.store),
            )
            graph = build_email_action_graph(
                checkpointer=postgres.checkpointer,
                store=postgres.store,
                execution_ledger=postgres.execution_ledger,
                write_executor=executor,
            )
            results = await GmailWorkflowWorker(
                transport, planner, graph, index
            ).poll_once(max_messages=args.max_messages)
            for result in results:
                print(
                    f"message={result.message_id} status={result.status} "
                    f"thread={result.thread_id} error={result.error_code or '-'}"
                )
    finally:
        await index.close()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not 1 <= args.max_messages <= 20:
        raise SystemExit("--max-messages must be between 1 and 20")
    return asyncio.run(
        run_once(args),
        loop_factory=asyncio.SelectorEventLoop,
    )


if __name__ == "__main__":
    raise SystemExit(main())
