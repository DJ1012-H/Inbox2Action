from __future__ import annotations

import hashlib
import os
from uuid import uuid4

import pytest

from inbox2action.stage3 import (
    ActionProposal,
    ExecutionClaimOutcome,
    ExecutionResult,
    ExecutionStartOutcome,
    ExternalResourceRef,
)
from inbox2action.stage3.contracts import (
    ExecutionPermit,
    action_idempotency_key,
    payload_hash,
)
from inbox2action.stage4 import PostgresExecutionLedger, upgrade_database

pytestmark = pytest.mark.integration


def _database_url() -> str:
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS", "").lower() != "true":
        pytest.skip("set RUN_POSTGRES_INTEGRATION_TESTS=true for PostgreSQL tests")
    database_url = os.getenv("INBOX2ACTION_DATABASE_URL")
    if not database_url:
        pytest.fail("INBOX2ACTION_DATABASE_URL is required when PostgreSQL tests run")
    return database_url


def _permit(suffix: str) -> ExecutionPermit:
    proposal = ActionProposal(
        action_id=f"stage7-{suffix}",
        tool_name="save_task_proposal",
        parameters={
            "title": "Stage 7 PostgreSQL integration",
            "description": "Durable resource write-back test.",
            "priority": "high",
        },
    )
    return ExecutionPermit(
        thread_id=f"email:{hashlib.sha256(suffix.encode()).hexdigest()[:24]}",
        action_id=proposal.action_id,
        action=proposal,
        approved_payload_hash=payload_hash(proposal),
        idempotency_key=action_idempotency_key(
            "stage7-postgres", str(uuid4()), proposal
        ),
    )


@pytest.mark.asyncio
async def test_postgres_resource_writeback_and_unknown_reconciliation_survive_reopen() -> None:
    database_url = _database_url()
    upgrade_database(database_url)
    succeeded_permit = _permit("succeeded")
    unknown_permit = _permit("unknown")
    resource = ExternalResourceRef(
        provider="clickup",
        resource_type="task",
        resource_id="offline-stage7-task",
        url="https://app.clickup.com/t/offline-stage7-task",
    )
    succeeded = ExecutionResult(status="succeeded", resource=resource)

    ledger = PostgresExecutionLedger(database_url)
    try:
        assert await ledger.claim(succeeded_permit) is ExecutionClaimOutcome.CLAIMED
        assert await ledger.begin_execution(succeeded_permit) is ExecutionStartOutcome.STARTED
        await ledger.complete(succeeded_permit, succeeded)
        assert (
            await ledger.claim(succeeded_permit)
        ) is ExecutionClaimOutcome.ALREADY_SUCCEEDED
        assert await ledger.get_result(succeeded_permit) == succeeded

        assert await ledger.claim(unknown_permit) is ExecutionClaimOutcome.CLAIMED
        assert await ledger.begin_execution(unknown_permit) is ExecutionStartOutcome.STARTED
        unknown = ExecutionResult(
            status="unknown", error_code="clickup_reconciliation_unresolved"
        )
        await ledger.complete(unknown_permit, unknown)
        await ledger.reconcile_success(unknown_permit, succeeded)
    finally:
        await ledger.close()

    reopened = PostgresExecutionLedger(database_url)
    try:
        assert await reopened.get_result(succeeded_permit) == succeeded
        assert await reopened.get_result(unknown_permit) == succeeded
        assert (
            await reopened.claim(unknown_permit)
        ) is ExecutionClaimOutcome.ALREADY_SUCCEEDED
    finally:
        await reopened.close()
