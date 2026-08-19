from __future__ import annotations

import asyncio
from enum import Enum
from typing import Literal, Protocol

from inbox2action.stage3.contracts import ExecutionPermit, ExecutionResult


class ExecutionClaimOutcome(str, Enum):
    CLAIMED = "claimed"
    ALREADY_SUCCEEDED = "already_succeeded"
    BLOCKED_UNKNOWN = "blocked_unknown"


class ExecutionStartOutcome(str, Enum):
    STARTED = "started"
    ALREADY_SUCCEEDED = "already_succeeded"
    BLOCKED_UNKNOWN = "blocked_unknown"


class ReconciliationExecutor(Protocol):
    async def reconcile(self, permit: ExecutionPermit) -> ExecutionResult:
        """Resolve an UNKNOWN provider attempt using readonly reconciliation only."""


class ExecutionLedger(Protocol):
    async def claim(self, permit: ExecutionPermit) -> ExecutionClaimOutcome:
        """Durably claim an idempotency key before a provider side effect."""

    async def complete(
        self,
        permit: ExecutionPermit,
        result: ExecutionResult,
    ) -> None:
        """Record the provider outcome for the existing claim."""

    async def begin_execution(
        self,
        permit: ExecutionPermit,
    ) -> ExecutionStartOutcome:
        """Atomically start a fresh claim or classify a replay."""

    async def get_result(
        self,
        permit: ExecutionPermit,
    ) -> ExecutionResult | None:
        """Recover a terminal result bound to this exact approved permit."""

    async def reconcile_success(
        self,
        permit: ExecutionPermit,
        result: ExecutionResult,
    ) -> None:
        """Promote one UNKNOWN execution only after readonly reconciliation succeeds."""


class WriteExecutor(Protocol):
    async def execute(self, permit: ExecutionPermit) -> ExecutionResult:
        """Execute one already-approved and durably claimed write."""


class InMemoryExecutionLedger:
    """Deterministic ledger with the same no-replay decisions as PostgreSQL."""

    def __init__(self) -> None:
        self._records: dict[str, _InMemoryRecord] = {}
        self._lock = asyncio.Lock()

    async def claim(self, permit: ExecutionPermit) -> ExecutionClaimOutcome:
        async with self._lock:
            if permit.idempotency_key not in self._records:
                self._records[permit.idempotency_key] = _InMemoryRecord(
                    permit=permit,
                    value="claimed",
                )
                return ExecutionClaimOutcome.CLAIMED
            record = self._records[permit.idempotency_key]
            _validate_binding(record.permit, permit)
            if isinstance(record.value, ExecutionResult) and record.value.status == "succeeded":
                return ExecutionClaimOutcome.ALREADY_SUCCEEDED
            if isinstance(record.value, ExecutionResult) and record.value.status == "failed":
                record.value = "claimed"
                return ExecutionClaimOutcome.CLAIMED
            return ExecutionClaimOutcome.BLOCKED_UNKNOWN

    async def begin_execution(
        self,
        permit: ExecutionPermit,
    ) -> ExecutionStartOutcome:
        async with self._lock:
            record = self._records.get(permit.idempotency_key)
            if record is None:
                return ExecutionStartOutcome.BLOCKED_UNKNOWN
            _validate_binding(record.permit, permit)
            if isinstance(record.value, ExecutionResult) and record.value.status == "succeeded":
                return ExecutionStartOutcome.ALREADY_SUCCEEDED
            if record.value != "claimed":
                return ExecutionStartOutcome.BLOCKED_UNKNOWN
            record.value = "executing"
            return ExecutionStartOutcome.STARTED

    async def complete(
        self,
        permit: ExecutionPermit,
        result: ExecutionResult,
    ) -> None:
        async with self._lock:
            record = self._records.get(permit.idempotency_key)
            if record is None:
                raise RuntimeError("execution result has no durable claim")
            _validate_binding(record.permit, permit)
            if isinstance(record.value, ExecutionResult):
                if record.value == result:
                    return
                raise RuntimeError("execution claim already has a different result")
            if record.value != "executing":
                raise RuntimeError("execution claim was not started")
            record.value = result

    async def reconcile_success(
        self,
        permit: ExecutionPermit,
        result: ExecutionResult,
    ) -> None:
        if result.status != "succeeded" or result.resource is None:
            raise RuntimeError("reconciliation must provide a succeeded resource")
        async with self._lock:
            record = self._records.get(permit.idempotency_key)
            if record is None:
                raise RuntimeError("execution result has no durable claim")
            _validate_binding(record.permit, permit)
            if isinstance(record.value, ExecutionResult):
                if record.value.status == "succeeded" and record.value == result:
                    return
                if record.value.status == "unknown":
                    record.value = result
                    return
                raise RuntimeError("execution claim is not eligible for reconciliation")
            raise RuntimeError("execution claim is not eligible for reconciliation")

    async def get_result(self, permit: ExecutionPermit) -> ExecutionResult | None:
        async with self._lock:
            record = self._records.get(permit.idempotency_key)
            if record is None:
                return None
            _validate_binding(record.permit, permit)
            return record.value if isinstance(record.value, ExecutionResult) else None

    def result(self, idempotency_key: str) -> ExecutionResult | None:
        record = self._records.get(idempotency_key)
        if record is None:
            return None
        return record.value if isinstance(record.value, ExecutionResult) else None


class _InMemoryRecord:
    def __init__(
        self,
        *,
        permit: ExecutionPermit,
        value: ExecutionResult | LiteralStatus,
    ) -> None:
        self.permit = permit
        self.value = value


def _validate_binding(expected: ExecutionPermit, actual: ExecutionPermit) -> None:
    if (
        expected.idempotency_key != actual.idempotency_key
        or
        expected.thread_id != actual.thread_id
        or expected.action_id != actual.action_id
        or expected.approved_payload_hash != actual.approved_payload_hash
    ):
        raise RuntimeError("idempotency key is bound to another action payload")


LiteralStatus = Literal["claimed", "executing"]
