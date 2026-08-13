from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore

from inbox2action.stage4.persistence import PostgresExecutionLedger


@dataclass(frozen=True)
class LangGraphPostgresRuntime:
    checkpointer: AsyncPostgresSaver
    store: AsyncPostgresStore
    execution_ledger: PostgresExecutionLedger


@asynccontextmanager
async def open_langgraph_postgres(
    database_url: str,
) -> AsyncIterator[LangGraphPostgresRuntime]:
    """Open and initialize the Stage 4 LangGraph PostgreSQL resources."""

    async with AsyncPostgresSaver.from_conn_string(database_url) as checkpointer:
        await checkpointer.setup()
        async with AsyncPostgresStore.from_conn_string(database_url) as store:
            await store.setup()
            execution_ledger = PostgresExecutionLedger(database_url)
            try:
                yield LangGraphPostgresRuntime(
                    checkpointer=checkpointer,
                    store=store,
                    execution_ledger=execution_ledger,
                )
            finally:
                await execution_ledger.close()
