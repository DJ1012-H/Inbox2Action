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


class WriteExecutor(Protocol):
    async def execute(self, permit: ExecutionPermit) -> ExecutionResult:
        """Execute one already-approved and durably claimed write."""


class InMemoryExecutionLedger:
    """Deterministic ledger with the same no-replay decisions as PostgreSQL."""

    def __init__(self) -> None:
        self._records: dict[str, ExecutionResult | LiteralStatus] = {}
        self._lock = asyncio.Lock()

    async def claim(self, permit: ExecutionPermit) -> ExecutionClaimOutcome:
        async with self._lock:
            if permit.idempotency_key not in self._records:
                self._records[permit.idempotency_key] = "claimed"
                return ExecutionClaimOutcome.CLAIMED
            result = self._records[permit.idempotency_key]
            if isinstance(result, ExecutionResult) and result.status == "succeeded":
                return ExecutionClaimOutcome.ALREADY_SUCCEEDED
            if isinstance(result, ExecutionResult) and result.status == "failed":
                self._records[permit.idempotency_key] = "claimed"
                return ExecutionClaimOutcome.CLAIMED
            return ExecutionClaimOutcome.BLOCKED_UNKNOWN

    async def begin_execution(
        self,
        permit: ExecutionPermit,
    ) -> ExecutionStartOutcome:
        async with self._lock:
            current = self._records.get(permit.idempotency_key)
            if isinstance(current, ExecutionResult) and current.status == "succeeded":
                return ExecutionStartOutcome.ALREADY_SUCCEEDED
            if current != "claimed":
                return ExecutionStartOutcome.BLOCKED_UNKNOWN
            self._records[permit.idempotency_key] = "executing"
            return ExecutionStartOutcome.STARTED

    async def complete(
        self,
        permit: ExecutionPermit,
        result: ExecutionResult,
    ) -> None:
        async with self._lock:
            if permit.idempotency_key not in self._records:
                raise RuntimeError("execution result has no durable claim")
            current = self._records[permit.idempotency_key]
            if isinstance(current, ExecutionResult):
                if current == result:
                    return
                raise RuntimeError("execution claim already has a different result")
            if current != "executing":
                raise RuntimeError("execution claim was not started")
            self._records[permit.idempotency_key] = result

    def result(self, idempotency_key: str) -> ExecutionResult | None:
        result = self._records.get(idempotency_key)
        return result if isinstance(result, ExecutionResult) else None


LiteralStatus = Literal["claimed", "executing"]
