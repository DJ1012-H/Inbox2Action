from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from inbox2action.stage3.contracts import ExecutionPermit, ExecutionResult
from inbox2action.stage3.execution import (
    ExecutionClaimOutcome,
    ExecutionStartOutcome,
)

metadata = MetaData()
execution_ledger_table = Table(
    "inbox2action_execution_ledger",
    metadata,
    Column("idempotency_key", String(64), primary_key=True),
    Column("thread_id", String(30), nullable=False),
    Column("action_id", String(128), nullable=False),
    Column("payload_hash", String(64), nullable=False),
    Column("status", String(16), nullable=False),
    Column("error_code", String(64), nullable=True),
    Column("attempt_count", BigInteger, nullable=False),
    Column("claimed_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


class PostgresExecutionLedger:
    """Durable side-effect claim ledger; LangGraph remains the state source."""

    def __init__(self, database_url: str) -> None:
        self._engine: AsyncEngine = create_async_engine(_sqlalchemy_url(database_url))

    async def claim(self, permit: ExecutionPermit) -> ExecutionClaimOutcome:
        now = datetime.now(UTC)
        async with self._engine.begin() as connection:
            inserted = await connection.execute(
                postgres_insert(execution_ledger_table)
                .values(
                    idempotency_key=permit.idempotency_key,
                    thread_id=permit.thread_id,
                    action_id=permit.action_id,
                    payload_hash=permit.approved_payload_hash,
                    status="claimed",
                    error_code=None,
                    attempt_count=1,
                    claimed_at=now,
                    updated_at=now,
                )
                .on_conflict_do_nothing(
                    index_elements=[execution_ledger_table.c.idempotency_key]
                )
                .returning(execution_ledger_table.c.idempotency_key)
            )
            if inserted.scalar_one_or_none() is not None:
                return ExecutionClaimOutcome.CLAIMED

            row = (
                await connection.execute(
                    select(execution_ledger_table)
                    .where(
                        execution_ledger_table.c.idempotency_key
                        == permit.idempotency_key
                    )
                    .with_for_update()
                )
            ).mappings().one()
            if (
                row["thread_id"] != permit.thread_id
                or row["action_id"] != permit.action_id
                or row["payload_hash"] != permit.approved_payload_hash
            ):
                raise RuntimeError("idempotency key is bound to another action payload")
            if row["status"] == "succeeded":
                return ExecutionClaimOutcome.ALREADY_SUCCEEDED
            if row["status"] == "failed":
                await connection.execute(
                    update(execution_ledger_table)
                    .where(
                        execution_ledger_table.c.idempotency_key
                        == permit.idempotency_key
                    )
                    .values(
                        status="claimed",
                        error_code=None,
                        attempt_count=int(row["attempt_count"]) + 1,
                        claimed_at=now,
                        updated_at=now,
                    )
                )
                return ExecutionClaimOutcome.CLAIMED
            return ExecutionClaimOutcome.BLOCKED_UNKNOWN

    async def complete(
        self,
        permit: ExecutionPermit,
        result: ExecutionResult,
    ) -> None:
        now = datetime.now(UTC)
        async with self._engine.begin() as connection:
            row = (
                await connection.execute(
                    select(execution_ledger_table.c.status)
                    .where(
                        execution_ledger_table.c.idempotency_key
                        == permit.idempotency_key
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if row is None:
                raise RuntimeError("execution result has no durable claim")
            if row == result.status:
                return
            if row != "executing":
                raise RuntimeError("execution claim already has a terminal result")
            changed = await connection.execute(
                update(execution_ledger_table)
                .where(
                    execution_ledger_table.c.idempotency_key
                    == permit.idempotency_key
                )
                .where(execution_ledger_table.c.status == "executing")
                .values(
                    status=result.status,
                    error_code=result.error_code,
                    updated_at=now,
                )
            )
            if changed.rowcount != 1:
                raise RuntimeError("execution ledger update lost its claim")

    async def begin_execution(
        self,
        permit: ExecutionPermit,
    ) -> ExecutionStartOutcome:
        now = datetime.now(UTC)
        async with self._engine.begin() as connection:
            status = (
                await connection.execute(
                    select(execution_ledger_table.c.status)
                    .where(
                        execution_ledger_table.c.idempotency_key
                        == permit.idempotency_key
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if status == "succeeded":
                return ExecutionStartOutcome.ALREADY_SUCCEEDED
            if status != "claimed":
                return ExecutionStartOutcome.BLOCKED_UNKNOWN
            await connection.execute(
                update(execution_ledger_table)
                .where(
                    execution_ledger_table.c.idempotency_key
                    == permit.idempotency_key
                )
                .where(execution_ledger_table.c.status == "claimed")
                .values(status="executing", updated_at=now)
            )
            return ExecutionStartOutcome.STARTED

    async def close(self) -> None:
        await self._engine.dispose()


def _sqlalchemy_url(database_url: str) -> str:
    if database_url.startswith("postgresql+psycopg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    raise ValueError("database URL must use PostgreSQL")
