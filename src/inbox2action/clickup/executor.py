"""HITL-approved, ledger-guarded ClickUp task write adapter."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from inbox2action.stage3.contracts import (
    ExecutionPermit,
    ExecutionResult,
    ExternalResourceRef,
)
from inbox2action.tools.schemas import CreateClickUpTaskArgs

from .client import ClickUpClient
from .errors import (
    ClickUpAuthenticationError,
    ClickUpConfigurationError,
    ClickUpError,
    ClickUpForbiddenError,
    ClickUpInvalidRequestError,
    ClickUpInvalidResponseError,
    ClickUpNotFoundError,
    ClickUpRateLimitedError,
    ClickUpTimeoutError,
    ClickUpUnavailableError,
)

if TYPE_CHECKING:
    from inbox2action.config import Settings


class ClickUpWriteExecutor:
    """Translate an approved proposal into one guarded POST and readonly recovery."""

    def __init__(
        self,
        client: ClickUpClient | None = None,
        *,
        enabled: bool = False,
        startup_error: str | None = None,
        reconciliation_attempts: int = 3,
        sleeper: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        if (
            isinstance(reconciliation_attempts, bool)
            or not isinstance(reconciliation_attempts, int)
            or not 1 <= reconciliation_attempts <= 3
        ):
            raise ValueError("reconciliation_attempts must be between 1 and 3")
        self._client = client
        self._enabled = enabled
        self._startup_error = startup_error
        self._reconciliation_attempts = reconciliation_attempts
        self._sleeper = sleeper or asyncio.sleep

    @classmethod
    def from_settings(cls, settings: Settings) -> ClickUpWriteExecutor:
        """Build a fail-closed adapter after readonly marker-field preflight."""

        if not settings.clickup_enabled:
            return cls(enabled=False)
        token = settings.clickup_api_token_value
        list_id = settings.clickup_list_id
        if token is None or list_id is None:
            return cls(enabled=True)
        try:
            client = ClickUpClient(
                api_token=token,
                list_id=list_id,
                timeout_seconds=settings.clickup_timeout_seconds,
            )
        except ClickUpConfigurationError:
            return cls(enabled=True, startup_error="clickup_configuration")
        try:
            client.resolve_idempotency_field()
        except ClickUpError as error:
            return cls(enabled=True, startup_error=f"clickup_preflight_{error.code}")
        return cls(client, enabled=True)

    async def execute(self, permit: ExecutionPermit) -> ExecutionResult:
        """Execute only the already-authorized local task-proposal translation."""

        if not self._enabled:
            return _failed("clickup_disabled")
        if self._startup_error is not None:
            return _failed(self._startup_error)
        if self._client is None:
            return _failed("clickup_configuration")
        if permit.action.tool_name != "save_task_proposal":
            return _failed("clickup_unsupported_tool")

        try:
            self._client.resolve_idempotency_field()
            proposal = CreateClickUpTaskArgs.model_validate(permit.action.parameters)
        except ValueError:
            return _failed("clickup_invalid_request")
        except ClickUpError as error:
            return _failed(f"clickup_preflight_{error.code}")

        try:
            created = self._client.create_task(
                title=proposal.title,
                description=proposal.description,
                due_at=proposal.due_at,
                priority=proposal.priority,
                idempotency_key=permit.idempotency_key,
            )
        except ClickUpInvalidRequestError:
            return _failed("clickup_invalid_request")
        except (
            ClickUpAuthenticationError,
            ClickUpForbiddenError,
            ClickUpNotFoundError,
            ClickUpRateLimitedError,
        ) as error:
            return _failed(f"clickup_{error.code}")
        except ClickUpConfigurationError:
            return _failed("clickup_configuration")
        except (ClickUpTimeoutError, ClickUpUnavailableError):
            return await self.reconcile(permit)
        except ClickUpInvalidResponseError:
            return await self.reconcile(permit)
        except ClickUpError:
            return _unknown("clickup_provider_error")
        except Exception:  # noqa: BLE001 - transport ambiguity must block replay
            return await self.reconcile(permit)

        return ExecutionResult(
            status="succeeded",
            resource=ExternalResourceRef(
                provider="clickup",
                resource_type="task",
                resource_id=created.task_id,
                url=created.url,
            ),
        )

    async def reconcile(self, permit: ExecutionPermit) -> ExecutionResult:
        """Recover one ambiguous POST with bounded GET-only reconciliation."""

        if not self._enabled:
            return _unknown("clickup_disabled")
        if self._startup_error is not None:
            return _unknown(self._startup_error)
        if self._client is None:
            return _unknown("clickup_configuration")
        if permit.action.tool_name != "save_task_proposal":
            return _unknown("clickup_unsupported_tool")
        try:
            self._client.resolve_idempotency_field()
        except ClickUpError as error:
            return _unknown(f"clickup_preflight_{error.code}")

        for attempt in range(self._reconciliation_attempts):
            if attempt:
                await self._sleeper(float(attempt))
            try:
                tasks = self._client.find_tasks_by_idempotency_key(
                    permit.idempotency_key
                )
            except ClickUpError:
                if attempt + 1 < self._reconciliation_attempts:
                    continue
                return _unknown("clickup_reconciliation_failed")
            if len(tasks) == 1:
                task = tasks[0]
                return ExecutionResult(
                    status="succeeded",
                    resource=ExternalResourceRef(
                        provider="clickup",
                        resource_type="task",
                        resource_id=task.task_id,
                        url=task.url,
                    ),
                )
            if len(tasks) > 1:
                return _unknown("clickup_reconciliation_conflict")
        return _unknown("clickup_reconciliation_unresolved")


def _failed(error_code: str) -> ExecutionResult:
    return ExecutionResult(status="failed", error_code=error_code)


def _unknown(error_code: str) -> ExecutionResult:
    return ExecutionResult(status="unknown", error_code=error_code)
