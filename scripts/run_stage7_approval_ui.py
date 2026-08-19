"""Run the HITL approval UI with the Stage 7 ClickUp write boundary."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence

from inbox2action.clickup import ClickUpWriteExecutor
from inbox2action.config import Settings
from inbox2action.stage3 import build_email_action_graph
from inbox2action.stage4 import open_langgraph_postgres, upgrade_database
from inbox2action.stage6 import ApprovalService, PostgresWorkflowIndex
from inbox2action.stage6.server import serve_approval_ui


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Serve the local Stage 7 HITL approval page with ClickUp writes guarded by the ledger."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    return parser


async def run_server(args: argparse.Namespace) -> int:
    settings = Settings()
    database_url = settings.database_url_value
    if not database_url:
        raise SystemExit(
            "INBOX2ACTION_DATABASE_URL must be configured in runtime.env or the process environment"
        )
    upgrade_database(database_url)
    index = PostgresWorkflowIndex(database_url)
    executor = ClickUpWriteExecutor.from_settings(settings)
    try:
        async with open_langgraph_postgres(database_url) as runtime:
            graph = build_email_action_graph(
                checkpointer=runtime.checkpointer,
                store=runtime.store,
                execution_ledger=runtime.execution_ledger,
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
