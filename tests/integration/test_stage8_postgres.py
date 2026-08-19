from __future__ import annotations

import hashlib
import os
from uuid import uuid4

import pytest

from inbox2action.stage3 import (
    ActionProposal,
    ExecutionClaimOutcome,
    ExecutionPermit,
    ExecutionResult,
    ExecutionStartOutcome,
    ExternalResourceRef,
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


def _permit() -> ExecutionPermit:
    proposal = ActionProposal(
        action_id="stage8-calendar-event",
        tool_name="save_calendar_proposal",
        parameters={
            "summary": "Stage 8 Calendar integration",
            "description": "Generic resource persistence test.",
            "start_time": "2026-08-21T16:00:00+08:00",
            "end_time": "2026-08-21T17:00:00+08:00",
            "timezone": "Asia/Shanghai",
            "location": None,
        },
    )
    return ExecutionPermit(
        thread_id=f"email:{hashlib.sha256(b'stage8-calendar').hexdigest()[:24]}",
        action_id=proposal.action_id,
        action=proposal,
        approved_payload_hash=payload_hash(proposal),
        idempotency_key=action_idempotency_key(
            "stage8-postgres", str(uuid4()), proposal
        ),
    )


@pytest.mark.asyncio
async def test_google_calendar_resource_survives_ledger_reopen_without_rewrite() -> None:
    database_url = _database_url()
    upgrade_database(database_url)
    permit = _permit()
    resource = ExternalResourceRef(
        provider="google_calendar",
        resource_type="event",
        resource_id="deterministic-google-event-id",
    )
    result = ExecutionResult(
        status="succeeded",
        resource=resource,
        diagnostics={
            "insert_attempt": {
                "outcome_class": "SUCCESS_RESPONSE",
                "response_received": True,
            },
            "reconciliation": None,
        },
    )
    provider_insert_count = 1

    ledger = PostgresExecutionLedger(database_url)
    try:
        assert await ledger.claim(permit) is ExecutionClaimOutcome.CLAIMED
        assert await ledger.begin_execution(permit) is ExecutionStartOutcome.STARTED
        await ledger.complete(permit, result)
    finally:
        await ledger.close()

    reopened = PostgresExecutionLedger(database_url)
    try:
        assert await reopened.claim(permit) is ExecutionClaimOutcome.ALREADY_SUCCEEDED
        assert await reopened.get_result(permit) == result
        assert provider_insert_count == 1
    finally:
        await reopened.close()
