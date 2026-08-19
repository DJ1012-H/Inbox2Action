from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

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

from inbox2action.stage3.contracts import (
    ExecutionPermit,
    ExecutionResult,
    ExternalResourceRef,
)
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
    Column("resource_provider", String(64), nullable=True),
    Column("resource_type", String(64), nullable=True),
    Column("resource_id", String(256), nullable=True),
    Column("resource_url", String(2048), nullable=True),
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
                        resource_provider=None,
                        resource_type=None,
                        resource_id=None,
                        resource_url=None,
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
                    select(execution_ledger_table)
                    .where(
                        execution_ledger_table.c.idempotency_key
                        == permit.idempotency_key
                    )
                    .with_for_update()
                )
            ).mappings().one_or_none()
            if row is None:
                raise RuntimeError("execution result has no durable claim")
            _validate_binding(row, permit)
            current_status = row["status"]
            if current_status in {"succeeded", "failed", "unknown"}:
                if _execution_result_from_row(row) == result:
                    return
                raise RuntimeError("execution claim already has a terminal result")
            if current_status != "executing":
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
                    resource_provider=(
                        result.resource.provider if result.resource is not None else None
                    ),
                    resource_type=(
                        result.resource.resource_type
                        if result.resource is not None
                        else None
                    ),
                    resource_id=(
                        result.resource.resource_id if result.resource is not None else None
                    ),
                    resource_url=(
                        result.resource.url if result.resource is not None else None
                    ),
                    updated_at=now,
                )
            )
            if changed.rowcount != 1:
                raise RuntimeError("execution ledger update lost its claim")

    async def reconcile_success(
        self,
        permit: ExecutionPermit,
        result: ExecutionResult,
    ) -> None:
        """Promote an UNKNOWN result only through the explicit readonly path."""

        if result.status != "succeeded" or result.resource is None:
            raise RuntimeError("reconciliation must provide a succeeded resource")
        now = datetime.now(UTC)
        async with self._engine.begin() as connection:
            row = (
                await connection.execute(
                    select(execution_ledger_table)
                    .where(
                        execution_ledger_table.c.idempotency_key
                        == permit.idempotency_key
                    )
                    .with_for_update()
                )
            ).mappings().one_or_none()
            if row is None:
                raise RuntimeError("execution result has no durable claim")
            _validate_binding(row, permit)
            current_status = row["status"]
            if current_status == "succeeded":
                if _execution_result_from_row(row) == result:
                    return
                raise RuntimeError("execution claim already has a different result")
            if current_status != "unknown":
                raise RuntimeError("execution claim is not eligible for reconciliation")
            changed = await connection.execute(
                update(execution_ledger_table)
                .where(
                    execution_ledger_table.c.idempotency_key
                    == permit.idempotency_key
                )
                .where(execution_ledger_table.c.status == "unknown")
                .values(
                    status="succeeded",
                    error_code=result.error_code,
                    resource_provider=result.resource.provider,
                    resource_type=result.resource.resource_type,
                    resource_id=result.resource.resource_id,
                    resource_url=result.resource.url,
                    updated_at=now,
                )
            )
            if changed.rowcount != 1:
                raise RuntimeError("execution ledger reconciliation lost its claim")

    async def begin_execution(
        self,
        permit: ExecutionPermit,
    ) -> ExecutionStartOutcome:
        now = datetime.now(UTC)
        async with self._engine.begin() as connection:
            status = (
                await connection.execute(
                    select(execution_ledger_table)
                    .where(
                        execution_ledger_table.c.idempotency_key
                        == permit.idempotency_key
                    )
                    .with_for_update()
                )
            ).mappings().one_or_none()
            if status is None:
                return ExecutionStartOutcome.BLOCKED_UNKNOWN
            _validate_binding(status, permit)
            if status["status"] == "succeeded":
                return ExecutionStartOutcome.ALREADY_SUCCEEDED
            if status["status"] != "claimed":
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

    async def get_result(self, permit: ExecutionPermit) -> ExecutionResult | None:
        async with self._engine.connect() as connection:
            row = (
                await connection.execute(
                    select(execution_ledger_table).where(
                        execution_ledger_table.c.idempotency_key
                        == permit.idempotency_key
                    )
                )
            ).mappings().one_or_none()
        if row is None:
            return None
        _validate_binding(row, permit)
        if row["status"] not in {"succeeded", "failed", "unknown"}:
            return None
        return _execution_result_from_row(row)

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


def _validate_binding(row: object, permit: ExecutionPermit) -> None:
    if not isinstance(row, Mapping):
        raise TypeError("execution ledger row is invalid")
    if (
        row.get("idempotency_key", permit.idempotency_key) != permit.idempotency_key
        or
        row["thread_id"] != permit.thread_id
        or row["action_id"] != permit.action_id
        or row["payload_hash"] != permit.approved_payload_hash
    ):
        raise RuntimeError("idempotency key is bound to another action payload")


def _execution_result_from_row(row: Mapping[Any, Any]) -> ExecutionResult:
    resource_values = (
        row["resource_provider"],
        row["resource_type"],
        row["resource_id"],
        row["resource_url"],
    )
    if all(value is None for value in resource_values):
        resource = None
    elif any(value is None for value in resource_values[:3]):
        raise RuntimeError("execution ledger resource reference is incomplete")
    else:
        resource = ExternalResourceRef.model_validate(
            {
                "provider": resource_values[0],
                "resource_type": resource_values[1],
                "resource_id": resource_values[2],
                "url": resource_values[3],
            }
        )
    return ExecutionResult.model_validate(
        {
            "status": row["status"],
            "error_code": row["error_code"],
            "resource": resource,
        }
    )
