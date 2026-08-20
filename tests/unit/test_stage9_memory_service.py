from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from inbox2action.evaluation.policy_v3 import (
    ActionNodeV3,
    ActionPlanV3,
    ParameterResolutionStatus,
    ParameterResolutionV3,
)
from inbox2action.evaluation.triage_v3 import TriageResultV3
from inbox2action.llm.models import TriageDecision
from inbox2action.memory import (
    MemoryCategory,
    MemoryService,
    MemoryUpdateOutcome,
    UserEditDiff,
)
from inbox2action.stage3 import (
    ActionProposal,
    EmailEnvelope,
    FixtureWriteExecutor,
    Stage2PlanningBundle,
    build_email_action_graph,
    prepare_workflow_state,
    workflow_state_to_graph,
)


@dataclass(frozen=True)
class _Item:
    value: dict[str, Any]


class _Store:
    def __init__(self) -> None:
        self.values: dict[tuple[tuple[str, ...], str], dict[str, Any]] = {}

    async def aget(
        self, namespace: tuple[str, ...], key: str, **_: Any
    ) -> _Item | None:
        value = self.values.get((namespace, key))
        return _Item(dict(value)) if value is not None else None

    async def aput(
        self,
        namespace: tuple[str, ...],
        key: str,
        value: dict[str, Any],
        **_: Any,
    ) -> None:
        self.values[(namespace, key)] = dict(value)

    async def asearch(self, namespace: tuple[str, ...], **_: Any) -> list[_Item]:
        return [
            _Item(dict(value))
            for (stored_namespace, _), value in self.values.items()
            if stored_namespace == namespace
            and value.get("record_type") == "memory_evidence"
        ]


def _task_diff(
    *, thread_id: str = "email:0123456789abcdef01234567", priority: str = "high"
) -> UserEditDiff:
    before = {"priority": "medium"}
    after = {"priority": priority}
    return UserEditDiff(
        category=MemoryCategory.TASK,
        thread_id=thread_id,
        action_id="task-1",
        approval_revision=2,
        before=before,
        after=after,
        preference_updates={"default_priority": priority},
    )


@pytest.mark.asyncio
async def test_update_is_idempotent_across_service_reopen_and_versioned() -> None:
    store = _Store()
    first = MemoryService(store)
    diff = _task_diff()

    owner = "stage9-memory@example.test"
    outcome, document = await first.apply_user_edit(owner, diff)
    assert outcome is MemoryUpdateOutcome.APPLIED
    assert document.version == 1
    assert document.typed_preferences().default_priority == "high"

    reopened = MemoryService(store)
    duplicate, duplicate_document = await reopened.apply_user_edit(
        owner, diff
    )
    assert duplicate is MemoryUpdateOutcome.ALREADY_APPLIED
    assert duplicate_document.version == 1
    assert duplicate_document.evidence_count == 1

    no_op = UserEditDiff(
        category=MemoryCategory.TASK,
        thread_id=diff.thread_id,
        action_id=diff.action_id,
        approval_revision=diff.approval_revision,
        before={"priority": "medium"},
        after={"priority": "medium"},
    )
    no_op_outcome, no_op_document = await reopened.apply_user_edit(
        owner, no_op
    )
    assert no_op_outcome is MemoryUpdateOutcome.NO_OP
    assert no_op_document.version == 1


@pytest.mark.asyncio
async def test_real_langgraph_inmemory_store_accepts_email_like_owner_namespace() -> None:
    store = InMemoryStore()
    service = MemoryService(store)
    diff = _task_diff()

    applied, document = await service.apply_user_edit(
        "stage9-memory@example.test", diff
    )
    replayed, replayed_document = await MemoryService(store).apply_user_edit(
        "stage9-memory@example.test", diff
    )

    assert applied is MemoryUpdateOutcome.APPLIED
    assert document.version == 1
    assert replayed is MemoryUpdateOutcome.ALREADY_APPLIED
    assert replayed_document.version == 1
    assert (
        await service.load("stage9-memory@example.test", MemoryCategory.TASK)
    ).typed_preferences().default_priority == "high"


@pytest.mark.asyncio
async def test_accounts_are_isolated_and_triage_is_category_aware() -> None:
    service = MemoryService(_Store())
    await service.apply_user_edit("a@example.test", _task_diff())
    triage = UserEditDiff.from_triage_correction(
        thread_id="email:0123456789abcdef01234568",
        approval_revision=1,
        message_type="newsletter",
        before_decision="NOTIFY",
        after_decision="IGNORE",
    )
    await service.apply_user_edit("a@example.test", triage)

    a_context = await service.load_context("A@example.test")
    b_context = await service.load_context("b@example.test")
    assert a_context.task.default_priority == "high"
    assert a_context.triage.ignored_types == ("newsletter",)
    assert b_context.task.default_priority is None
    assert b_context.triage.ignored_types == ()
    assert a_context.versions[MemoryCategory.TASK] == 1
    assert a_context.versions[MemoryCategory.TRIAGE] == 1


@pytest.mark.asyncio
async def test_corrupt_or_malicious_state_is_ignored_fail_closed() -> None:
    store = _Store()
    namespace = MemoryService.namespace(
        "stage9-memory@example.test", MemoryCategory.TASK
    )
    await store.aput(
        namespace,
        "memory",
        {
            "record_type": "memory_state",
            "category": "task_preferences",
            "schema_version": 1,
            "version": 0,
            "evidence_count": 0,
            "preferences": {"default_priority": "high", "clickup_list_id": "evil"},
            "updated_at": datetime.now(UTC).isoformat(),
        },
    )
    loaded = await MemoryService(store).load(
        "stage9-memory@example.test", MemoryCategory.TASK
    )
    assert loaded.version == 0
    assert loaded.typed_preferences().default_priority is None


@pytest.mark.asyncio
async def test_existing_hitl_edit_updates_memory_without_a_second_approval_system() -> (
    None
):
    store = _Store()
    triage = TriageResultV3(
        decision=TriageDecision.ACTION_REQUIRED,
        reason="task request",
        confidence=1.0,
        suspected_prompt_injection=False,
        security_reason=None,
        safe_to_plan_actions=True,
    )
    proposal = ActionProposal(
        action_id="task-1",
        tool_name="save_task_proposal",
        parameters={
            "title": "Prepare report",
            "description": "Summarize results",
            "priority": "medium",
        },
    )
    action = ActionNodeV3(
        action_id="task-1",
        tool_name="save_task_proposal",
        required_parameters=("title", "description", "priority"),
        parameter_resolutions=tuple(
            ParameterResolutionV3(
                field_name=field,
                status=ParameterResolutionStatus.RESOLVED,
                source="test",
            )
            for field in ("title", "description", "priority")
        ),
        requires_approval=True,
    )
    state = prepare_workflow_state(
        EmailEnvelope(
            account_id="a@example.test",
            message_id="message-memory-hitl",
            subject="Task",
            body="Please prepare a report.",
        ),
        Stage2PlanningBundle(
            triage=triage,
            action_plan=ActionPlanV3(actions=(action,)),
            proposals=[proposal],
        ),
    )
    graph = build_email_action_graph(
        checkpointer=InMemorySaver(),
        store=store,  # the same Store boundary used by production PostgresStore
        write_executor=FixtureWriteExecutor(),
    )
    config = {"configurable": {"thread_id": state.thread_id}}
    first = await graph.ainvoke(workflow_state_to_graph(state), config)
    assert first["__interrupt__"][0].value["revision"] == 1

    edited = await graph.ainvoke(
        Command(
            resume={
                "decision": "edit",
                "expected_revision": 1,
                "parameters": {**proposal.parameters, "priority": "high"},
            }
        ),
        config,
    )
    assert edited["__interrupt__"][0].value["revision"] == 2
    document = await MemoryService(store).load("a@example.test", MemoryCategory.TASK)
    assert document.version == 1
    assert document.typed_preferences().default_priority == "high"
