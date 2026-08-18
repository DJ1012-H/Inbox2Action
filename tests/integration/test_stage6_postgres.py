from __future__ import annotations

import os
from dataclasses import dataclass
from uuid import uuid4

import pytest

from inbox2action.evaluation.policy_v3 import (
    ActionNodeV3,
    ActionPlanV3,
    ParameterResolutionStatus,
    ParameterResolutionV3,
)
from inbox2action.evaluation.triage_v3 import TriageResultV3
from inbox2action.gmail import GmailMessage, GmailMessageSummary, GmailProfile
from inbox2action.llm.models import TriageDecision
from inbox2action.stage3 import (
    ActionProposal,
    FixtureWriteExecutor,
    Stage2PlanningBundle,
    build_email_action_graph,
)
from inbox2action.stage3.contracts import EmailEnvelope
from inbox2action.stage4 import open_langgraph_postgres, upgrade_database
from inbox2action.stage6 import (
    ApprovalService,
    GmailWorkflowWorker,
    PostgresWorkflowIndex,
)

pytestmark = pytest.mark.integration


def _database_url() -> str:
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS", "").lower() != "true":
        pytest.skip("set RUN_POSTGRES_INTEGRATION_TESTS=true for PostgreSQL tests")
    database_url = os.getenv("INBOX2ACTION_DATABASE_URL")
    if not database_url:
        pytest.fail("INBOX2ACTION_DATABASE_URL is required when PostgreSQL tests run")
    return database_url


@dataclass
class _Transport:
    profile: GmailProfile
    summary: GmailMessageSummary
    message: GmailMessage

    def get_profile(self) -> GmailProfile:
        return self.profile

    def read_recent_messages(self, max_messages: int = 10) -> list[GmailMessageSummary]:
        return [self.summary][:max_messages]

    def read_message(
        self, message_id: str, *, thread_id: str | None = None
    ) -> GmailMessage:
        assert message_id == self.message.message_id
        return self.message


@dataclass
class _Planner:
    bundle: Stage2PlanningBundle

    def plan(self, envelope: EmailEnvelope) -> Stage2PlanningBundle:
        assert envelope.message_id
        return self.bundle


def _bundle() -> Stage2PlanningBundle:
    action = ActionNodeV3(
        action_id="stage6-postgres-draft",
        tool_name="save_reply_draft",
        required_parameters=("subject", "body"),
        parameter_resolutions=(
            ParameterResolutionV3(
                field_name="subject",
                status=ParameterResolutionStatus.RESOLVED,
                source="integration",
            ),
            ParameterResolutionV3(
                field_name="body",
                status=ParameterResolutionStatus.RESOLVED,
                source="integration",
            ),
        ),
        requires_approval=True,
    )
    return Stage2PlanningBundle(
        triage=TriageResultV3(
            decision=TriageDecision.ACTION_REQUIRED,
            reason="persistent Stage 6 integration",
            confidence=1.0,
            suspected_prompt_injection=False,
            security_reason=None,
            safe_to_plan_actions=True,
        ),
        action_plan=ActionPlanV3(actions=(action,)),
        proposals=[
            ActionProposal(
                action_id="stage6-postgres-draft",
                tool_name="save_reply_draft",
                parameters={
                    "recipient": "sender@example.test",
                    "subject": "Re: Persistent Stage 6 approval",
                    "body": "Received.",
                },
            )
        ],
    )


@pytest.mark.asyncio
async def test_stage6_postgres_interrupt_reopen_and_approve() -> None:
    database_url = _database_url()
    upgrade_database(database_url)
    message_id = f"stage6-{uuid4()}"
    bundle = _bundle()
    transport = _Transport(
        profile=GmailProfile(email_address="stage6-postgres@example.test"),
        summary=GmailMessageSummary(
            message_id=message_id,
            thread_id="gmail-stage6-postgres",
            from_address="sender@example.test",
            subject="Persistent Stage 6 approval",
            date="2026-08-16T10:00:00+08:00",
        ),
        message=GmailMessage(
            message_id=message_id,
            thread_id="gmail-stage6-postgres",
            from_address="sender@example.test",
            reply_to="",
            subject="Persistent Stage 6 approval",
            date="2026-08-16T10:00:00+08:00",
            body="Please prepare a reply.",
            html=None,
        ),
    )
    index = PostgresWorkflowIndex(database_url)
    executor = FixtureWriteExecutor()
    try:
        async with open_langgraph_postgres(database_url) as runtime:
            graph = build_email_action_graph(
                checkpointer=runtime.checkpointer,
                store=runtime.store,
                execution_ledger=runtime.execution_ledger,
                write_executor=executor,
            )
            result = await GmailWorkflowWorker(
                transport, _Planner(bundle), graph, index
            ).poll_once(max_messages=1)

        assert result[0].status == "waiting_for_approval"
        pending = await index.list_pending()
        assert len(pending) == 1

        async with open_langgraph_postgres(database_url) as reopened_runtime:
            reopened_graph = build_email_action_graph(
                checkpointer=reopened_runtime.checkpointer,
                store=reopened_runtime.store,
                execution_ledger=reopened_runtime.execution_ledger,
                write_executor=executor,
            )
            service = ApprovalService(reopened_graph, index)
            view = (await service.list_pending())[0]
            completed = await service.decide(
                view["thread_id"],
                operation="approve",
                expected_revision=view["approval_revision"],
                action_id=view["current_action_id"],
            )

        assert completed["status"] == "completed"
        assert len(executor.calls) == 1
    finally:
        await index.close()
