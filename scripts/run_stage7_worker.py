"""Run one bounded Gmail-to-HITL polling pass with the Stage 7 write boundary."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence

from inbox2action.clickup import ClickUpWriteExecutor
from inbox2action.config import Settings, resolve_configured_path
from inbox2action.gmail import (
    GmailOAuthConfig,
    GmailOAuthCredentialProvider,
    GmailReadonlyTransport,
)
from inbox2action.llm import OpenAIChatClient
from inbox2action.memory import MemoryService
from inbox2action.stage3 import build_email_action_graph
from inbox2action.stage4 import open_langgraph_postgres, upgrade_database
from inbox2action.stage6 import (
    GmailStage2Planner,
    GmailWorkflowWorker,
    PostgresWorkflowIndex,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Poll bounded Gmail and pause at HITL before the Stage 7 ClickUp write boundary."
    )
    parser.add_argument(
        "--client-secrets",
        default=None,
        help="External Desktop OAuth client JSON path; overrides Settings.",
    )
    parser.add_argument(
        "--token-path",
        default=None,
        help="External OAuth token path; overrides Settings.",
    )
    parser.add_argument("--max-messages", type=int, default=10)
    return parser


async def run_once(args: argparse.Namespace) -> int:
    settings = Settings()
    database_url = settings.database_url_value
    if not database_url:
        raise SystemExit(
            "INBOX2ACTION_DATABASE_URL must be configured in runtime.env or the process environment"
        )
    try:
        client_secrets_path = resolve_configured_path(
            args.client_secrets,
            settings.gmail_client_secrets_path,
            setting_name="GMAIL_CLIENT_SECRETS_PATH or --client-secrets",
        )
        token_path = resolve_configured_path(
            args.token_path,
            settings.gmail_token_path,
            setting_name="GMAIL_TOKEN_PATH or --token-path",
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error

    upgrade_database(database_url)
    transport = GmailReadonlyTransport(
        GmailOAuthCredentialProvider(
            GmailOAuthConfig(
                client_secrets_path=client_secrets_path,
                token_path=token_path,
            )
        )
    )
    index = PostgresWorkflowIndex(database_url)
    executor = ClickUpWriteExecutor.from_settings(settings)
    try:
        async with open_langgraph_postgres(database_url) as runtime:
            planner = GmailStage2Planner(
                OpenAIChatClient(settings),
                memory_service=MemoryService(runtime.store),
            )
            graph = build_email_action_graph(
                checkpointer=runtime.checkpointer,
                store=runtime.store,
                execution_ledger=runtime.execution_ledger,
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
