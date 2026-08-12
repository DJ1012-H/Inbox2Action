from __future__ import annotations

import os
from uuid import uuid4

import pytest
from langgraph.types import Command

from inbox2action.evaluation.policy_v3 import (
    ActionNodeV3,
    ActionPlanV3,
    ParameterResolutionStatus,
    ParameterResolutionV3,
)
from inbox2action.evaluation.triage_v3 import TriageResultV3
from inbox2action.llm.models import TriageDecision
from inbox2action.stage3 import (
    ActionProposal,
    EmailEnvelope,
    FixtureWriteExecutor,
    Stage2PlanningBundle,
    build_email_action_graph,
    prepare_workflow_state,
    workflow_state_to_graph,
)
from inbox2action.stage4 import open_langgraph_postgres, upgrade_database

pytestmark = pytest.mark.integration


def _database_url() -> str:
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS", "").lower() != "true":
        pytest.skip("set RUN_POSTGRES_INTEGRATION_TESTS=true for PostgreSQL tests")
    database_url = os.getenv("INBOX2ACTION_DATABASE_URL")
    if not database_url:
        pytest.fail("INBOX2ACTION_DATABASE_URL is required when PostgreSQL tests run")
    return database_url


def _prepared_state(message_id: str):
    triage = TriageResultV3(
        decision=TriageDecision.ACTION_REQUIRED,
        reason="PostgreSQL recovery integration",
        confidence=1.0,
        suspected_prompt_injection=False,
        security_reason=None,
        safe_to_plan_actions=True,
    )
    plan = ActionPlanV3(
        actions=(
            ActionNodeV3(
                action_id="postgres-draft",
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
            ),
        )
    )
    proposal = ActionProposal(
        action_id="postgres-draft",
        tool_name="save_reply_draft",
        parameters={
            "recipient": "person@example.test",
            "subject": "Re: Persistent approval",
            "body": "Received.",
        },
    )
    return prepare_workflow_state(
        EmailEnvelope(
            account_id="postgres-integration",
            message_id=message_id,
            from_address="person@example.test",
            subject="Persistent approval",
            body="Persist this proposal and resume it after reconnecting.",
        ),
        Stage2PlanningBundle(
            triage=triage,
            action_plan=plan,
            proposals=[proposal],
        ),
    )


@pytest.mark.asyncio
async def test_postgres_graph_interrupt_ledger_and_store_survive_reopen() -> None:
    database_url = _database_url()
    upgrade_database(database_url)
    state = _prepared_state(f"postgres-{uuid4()}")
    config = {"configurable": {"thread_id": state.thread_id}}
    preference_key = str(uuid4())

    async with open_langgraph_postgres(database_url) as runtime:
        graph = build_email_action_graph(
            checkpointer=runtime.checkpointer,
            store=runtime.store,
            execution_ledger=runtime.execution_ledger,
            write_executor=FixtureWriteExecutor(),
        )
        interrupted = await graph.ainvoke(workflow_state_to_graph(state), config)
        assert interrupted["__interrupt__"][0].value["revision"] == 1
        await runtime.store.aput(
            ("users", "postgres-integration"),
            preference_key,
            {"timezone": "Asia/Shanghai"},
        )

    executor = FixtureWriteExecutor()
    async with open_langgraph_postgres(database_url) as reopened_runtime:
        reopened_graph = build_email_action_graph(
            checkpointer=reopened_runtime.checkpointer,
            store=reopened_runtime.store,
            execution_ledger=reopened_runtime.execution_ledger,
            write_executor=executor,
        )
        completed = await reopened_graph.ainvoke(
            Command(resume={"decision": "approve", "expected_revision": 1}),
            config,
        )
        preference = await reopened_runtime.store.aget(
            ("users", "postgres-integration"),
            preference_key,
        )

    assert completed["status"] == "completed"
    assert [permit.action_id for permit in executor.calls] == ["postgres-draft"]
    assert preference is not None
    assert preference.value == {"timezone": "Asia/Shanghai"}
