from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import (
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from inbox2action.stage4.persistence import _sqlalchemy_url

metadata = MetaData()
workflow_index_table = Table(
    "inbox2action_workflow_index",
    metadata,
    Column("thread_id", String(30), primary_key=True),
    Column("account_id", String(128), nullable=False),
    Column("message_id", String(256), nullable=False),
    Column("from_address", String(320), nullable=True),
    Column("subject", String(200), nullable=False),
    Column("received_at", String(64), nullable=True),
    Column("status", String(32), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "account_id", "message_id", name="uq_workflow_index_email_identity"
    ),
)


@dataclass(frozen=True)
class WorkflowIndexEntry:
    thread_id: str
    account_id: str
    message_id: str
    from_address: str | None
    subject: str
    received_at: str | None
    status: str
    updated_at: datetime


class WorkflowIndex(Protocol):
    async def reserve(
        self,
        *,
        thread_id: str,
        account_id: str,
        message_id: str,
        from_address: str | None,
        subject: str,
        received_at: str | None,
    ) -> bool: ...

    async def set_status(self, thread_id: str, status: str) -> None: ...

    async def list_pending(self) -> list[WorkflowIndexEntry]: ...


class InMemoryWorkflowIndex:
    """Deterministic index for local tests; production uses PostgreSQL."""

    def __init__(self) -> None:
        self.entries: dict[tuple[str, str], WorkflowIndexEntry] = {}

    async def reserve(
        self,
        *,
        thread_id: str,
        account_id: str,
        message_id: str,
        from_address: str | None,
        subject: str,
        received_at: str | None,
    ) -> bool:
        key = (account_id, message_id)
        if key in self.entries:
            return False
        now = datetime.now(UTC)
        self.entries[key] = WorkflowIndexEntry(
            thread_id=thread_id,
            account_id=account_id,
            message_id=message_id,
            from_address=from_address,
            subject=subject,
            received_at=received_at,
            status="processing",
            updated_at=now,
        )
        return True

    async def set_status(self, thread_id: str, status: str) -> None:
        for key, entry in self.entries.items():
            if entry.thread_id == thread_id:
                self.entries[key] = WorkflowIndexEntry(
                    thread_id=entry.thread_id,
                    account_id=entry.account_id,
                    message_id=entry.message_id,
                    from_address=entry.from_address,
                    subject=entry.subject,
                    received_at=entry.received_at,
                    status=status,
                    updated_at=datetime.now(UTC),
                )
                return
        raise KeyError(thread_id)

    async def list_pending(self) -> list[WorkflowIndexEntry]:
        return sorted(
            (
                entry
                for entry in self.entries.values()
                if entry.status == "waiting_for_approval"
            ),
            key=lambda entry: entry.updated_at,
            reverse=True,
        )


class PostgresWorkflowIndex:
    """Durable identity/status index; LangGraph remains the workflow state source."""

    def __init__(self, database_url: str) -> None:
        self._engine: AsyncEngine = create_async_engine(_sqlalchemy_url(database_url))

    async def reserve(
        self,
        *,
        thread_id: str,
        account_id: str,
        message_id: str,
        from_address: str | None,
        subject: str,
        received_at: str | None,
    ) -> bool:
        now = datetime.now(UTC)
        async with self._engine.begin() as connection:
            result = await connection.execute(
                postgres_insert(workflow_index_table)
                .values(
                    thread_id=thread_id,
                    account_id=account_id,
                    message_id=message_id,
                    from_address=from_address,
                    subject=subject,
                    received_at=received_at,
                    status="processing",
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_nothing(
                    constraint="uq_workflow_index_email_identity"
                )
                .returning(workflow_index_table.c.thread_id)
            )
            return result.scalar_one_or_none() is not None

    async def set_status(self, thread_id: str, status: str) -> None:
        async with self._engine.begin() as connection:
            changed = await connection.execute(
                update(workflow_index_table)
                .where(workflow_index_table.c.thread_id == thread_id)
                .values(status=status, updated_at=datetime.now(UTC))
            )
            if changed.rowcount != 1:
                raise KeyError(thread_id)

    async def list_pending(self) -> list[WorkflowIndexEntry]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    select(workflow_index_table)
                    .where(workflow_index_table.c.status == "waiting_for_approval")
                    .order_by(workflow_index_table.c.updated_at.desc())
                )
            ).mappings().all()
        return [_entry_from_row(row) for row in rows]

    async def close(self) -> None:
        await self._engine.dispose()


def _entry_from_row(row: object) -> WorkflowIndexEntry:
    mapping = row  # SQLAlchemy RowMapping supports string lookup at runtime.
    return WorkflowIndexEntry(
        thread_id=mapping["thread_id"],  # type: ignore[index]
        account_id=mapping["account_id"],  # type: ignore[index]
        message_id=mapping["message_id"],  # type: ignore[index]
        from_address=mapping["from_address"],  # type: ignore[index]
        subject=mapping["subject"],  # type: ignore[index]
        received_at=mapping["received_at"],  # type: ignore[index]
        status=mapping["status"],  # type: ignore[index]
        updated_at=mapping["updated_at"],  # type: ignore[index]
    )
