from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver
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
    ExecutionClaimOutcome,
    ExecutionResult,
    ExecutionStartOutcome,
    FixtureWriteExecutor,
    InMemoryExecutionLedger,
    Stage2PlanningBundle,
    build_email_action_graph,
    prepare_workflow_state,
    workflow_state_to_graph,
)


def _resolved(*names: str) -> tuple[ParameterResolutionV3, ...]:
    return tuple(
        ParameterResolutionV3(
            field_name=name,
            status=ParameterResolutionStatus.RESOLVED,
            source="reviewed_policy",
        )
        for name in names
    )


def _triage(decision: TriageDecision) -> TriageResultV3:
    return TriageResultV3(
        decision=decision,
        reason="reviewed Stage 2 handoff",
        confidence=1.0,
        suspected_prompt_injection=False,
        security_reason=None,
        safe_to_plan_actions=True,
    )


def _prepared_state(*, two_actions: bool = False):
    actions = [
        ActionNodeV3(
            action_id="draft-1",
            tool_name="save_reply_draft",
            required_parameters=("subject", "body"),
            parameter_resolutions=_resolved("subject", "body"),
            requires_approval=True,
        )
    ]
    proposals = [
        ActionProposal(
            action_id="draft-1",
            tool_name="save_reply_draft",
            parameters={
                "recipient": "person@example.test",
                "subject": "First action",
                "body": "Draft body",
            },
        )
    ]
    if two_actions:
        actions.append(
            ActionNodeV3(
                action_id="task-2",
                tool_name="create_clickup_task",
                depends_on=("draft-1",),
                required_parameters=("title", "description", "priority"),
                parameter_resolutions=_resolved(
                    "title",
                    "description",
                    "priority",
                ),
                requires_approval=True,
            )
        )
        proposals.append(
            ActionProposal(
                action_id="task-2",
                tool_name="create_clickup_task",
                parameters={
                    "title": "Follow up",
                    "description": "Track the approved reply",
                    "due_at": None,
                    "priority": "medium",
                },
            )
        )
    return prepare_workflow_state(
        EmailEnvelope(
            account_id="graph-account",
            message_id="graph-message",
            from_address="person@example.test",
            subject="Meeting request",
            body="Please prepare the requested actions.",
        ),
        Stage2PlanningBundle(
            triage=_triage(TriageDecision.ACTION_REQUIRED),
            action_plan=ActionPlanV3(actions=tuple(actions)),
            proposals=proposals,
        ),
    )


@pytest.mark.asyncio
async def test_real_interrupt_edit_then_approve_executes_exact_revision() -> None:
    state = _prepared_state()
    ledger = InMemoryExecutionLedger()
    executor = FixtureWriteExecutor()
    graph = build_email_action_graph(
        checkpointer=InMemorySaver(),
        execution_ledger=ledger,
        write_executor=executor,
    )
    config = {"configurable": {"thread_id": state.thread_id}}

    interrupted = await graph.ainvoke(workflow_state_to_graph(state), config)
    assert interrupted["__interrupt__"][0].value["revision"] == 1

    edited = await graph.ainvoke(
        Command(
            resume={
                "decision": "edit",
                "expected_revision": 1,
                "parameters": {
                    "recipient": "person@example.test",
                    "subject": "Edited action",
                    "body": "Edited body",
                },
            }
        ),
        config,
    )
    assert edited["__interrupt__"][0].value["revision"] == 2

    completed = await graph.ainvoke(
        Command(resume={"decision": "approve", "expected_revision": 2}),
        config,
    )
    assert completed["status"] == "completed"
    assert len(executor.calls) == 1
    assert executor.calls[0].action.parameters["subject"] == "Edited action"


@pytest.mark.asyncio
async def test_multi_action_plan_executes_in_dependency_order() -> None:
    state = _prepared_state(two_actions=True)
    executor = FixtureWriteExecutor()
    graph = build_email_action_graph(
        checkpointer=InMemorySaver(),
        execution_ledger=InMemoryExecutionLedger(),
        write_executor=executor,
    )
    config = {"configurable": {"thread_id": state.thread_id}}

    first = await graph.ainvoke(workflow_state_to_graph(state), config)
    assert first["__interrupt__"][0].value["action"]["action_id"] == "draft-1"
    second = await graph.ainvoke(
        Command(resume={"decision": "approve", "expected_revision": 1}),
        config,
    )
    assert second["__interrupt__"][0].value["action"]["action_id"] == "task-2"
    completed = await graph.ainvoke(
        Command(resume={"decision": "approve", "expected_revision": 1}),
        config,
    )

    assert completed["status"] == "completed"
    assert [permit.action_id for permit in executor.calls] == ["draft-1", "task-2"]


@pytest.mark.asyncio
async def test_rejection_is_a_terminal_resume_branch_without_write() -> None:
    state = _prepared_state()
    executor = FixtureWriteExecutor()
    graph = build_email_action_graph(
        checkpointer=InMemorySaver(),
        execution_ledger=InMemoryExecutionLedger(),
        write_executor=executor,
    )
    config = {"configurable": {"thread_id": state.thread_id}}

    await graph.ainvoke(workflow_state_to_graph(state), config)
    rejected = await graph.ainvoke(
        Command(resume={"decision": "reject", "expected_revision": 1}),
        config,
    )

    assert rejected["status"] == "rejected"
    assert executor.calls == []


@pytest.mark.asyncio
async def test_existing_unfinished_claim_blocks_replay_after_crash() -> None:
    state = _prepared_state()
    proposal = state.actions[0].proposal
    from inbox2action.stage3.contracts import (
        ActionStatus,
        ApprovalRecord,
        ApprovalStatus,
        WorkflowAction,
        payload_hash,
    )
    from inbox2action.stage3.workflow import authorize_execution

    digest = payload_hash(proposal)
    state = state.model_copy(
        update={
            "actions": [
                WorkflowAction(
                    proposal=proposal,
                    status=ActionStatus.APPROVED,
                    approval=ApprovalRecord(
                        action_id=proposal.action_id,
                        revision=1,
                        status=ApprovalStatus.APPROVED,
                        payload_hash=digest,
                        approved_payload_hash=digest,
                    ),
                )
            ],
            "current_action_id": proposal.action_id,
            "status": "approved",
        }
    )
    permit = authorize_execution(state, proposal.action_id)
    ledger = InMemoryExecutionLedger()

    assert await ledger.claim(permit) is ExecutionClaimOutcome.CLAIMED
    assert await ledger.begin_execution(permit) is ExecutionStartOutcome.STARTED
    assert (
        await ledger.begin_execution(permit)
        is ExecutionStartOutcome.BLOCKED_UNKNOWN
    )
    assert await ledger.claim(permit) is ExecutionClaimOutcome.BLOCKED_UNKNOWN
    await ledger.complete(permit, ExecutionResult(status="succeeded"))
    assert (
        await ledger.begin_execution(permit)
        is ExecutionStartOutcome.ALREADY_SUCCEEDED
    )
