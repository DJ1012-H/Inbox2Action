from __future__ import annotations

from typing import Any, Literal, TypedDict, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.base import BaseStore
from langgraph.types import interrupt

from inbox2action.stage3.contracts import (
    ActionProposal,
    ActionStatus,
    ApprovalDecision,
    ApprovalRecord,
    ApprovalStatus,
    AuditEvent,
    ExecutionResult,
    Stage3WorkflowStatus,
    WorkflowAction,
    WorkflowState,
    payload_hash,
)
from inbox2action.stage3.execution import (
    ExecutionClaimOutcome,
    ExecutionLedger,
    ExecutionStartOutcome,
    InMemoryExecutionLedger,
    WriteExecutor,
)
from inbox2action.stage3.workflow import (
    ApprovalError,
    InvalidTransitionError,
    authorize_execution,
    replace_workflow_action,
    workflow_action_for,
)


class EmailActionGraphState(TypedDict, total=False):
    """Durable channels; raw provider envelope is deliberately absent."""

    thread_id: str
    normalized_email: dict[str, object]
    triage: dict[str, object]
    status: str
    action_plan: dict[str, object] | None
    actions: list[dict[str, object]]
    completed_action_ids: list[str]
    current_action_id: str | None
    audit: list[dict[str, object]]


def workflow_state_to_graph(state: WorkflowState) -> EmailActionGraphState:
    return cast(EmailActionGraphState, state.model_dump(mode="json"))


def _state(value: EmailActionGraphState) -> WorkflowState:
    return WorkflowState.model_validate(value)


def _audit(
    state: WorkflowState,
    *,
    event_type: str,
    status: str,
    action_id: str | None = None,
    payload_hash_value: str | None = None,
    idempotency_key: str | None = None,
    error_code: str | None = None,
) -> list[dict[str, object]]:
    return [
        *(item.model_dump(mode="json") for item in state.audit),
        AuditEvent(
            event_type=event_type,
            status=status,
            action_id=action_id,
            payload_hash=payload_hash_value,
            idempotency_key=idempotency_key,
            error_code=error_code,
        ).model_dump(mode="json"),
    ]


def _validate_start_node(
    graph_state: EmailActionGraphState,
    config: RunnableConfig,
) -> EmailActionGraphState:
    state = _state(graph_state)
    configured_thread_id = config.get("configurable", {}).get("thread_id")
    if configured_thread_id != state.thread_id:
        raise InvalidTransitionError(
            "LangGraph configurable.thread_id must match workflow thread_id"
        )
    return {"status": state.status.value}


def _route_after_start(
    graph_state: EmailActionGraphState,
) -> Literal["select_next_action", "finalize"]:
    state = _state(graph_state)
    if state.status is Stage3WorkflowStatus.ACTION_REQUIRED:
        return "select_next_action"
    return "finalize"


def _select_next_action_node(
    graph_state: EmailActionGraphState,
) -> EmailActionGraphState:
    state = _state(graph_state)
    if state.action_plan is None:
        raise InvalidTransitionError("action-required workflow has no ActionPlanV3")

    for plan_action in state.action_plan.actions:
        candidates = [
            item
            for item in state.actions
            if item.proposal.action_id == plan_action.action_id
        ]
        if not candidates:
            continue
        action = candidates[0]
        if action.status in {
            ActionStatus.COMPLETED,
            ActionStatus.REJECTED,
            ActionStatus.FAILED,
            ActionStatus.UNKNOWN,
        }:
            continue
        if not set(plan_action.depends_on).issubset(state.completed_action_ids):
            continue
        if action.status is ActionStatus.PROPOSED:
            digest = payload_hash(action.proposal)
            action = action.model_copy(
                update={
                    "status": ActionStatus.WAITING_FOR_APPROVAL,
                    "approval": ApprovalRecord(
                        action_id=action.proposal.action_id,
                        revision=1,
                        status=ApprovalStatus.PENDING,
                        payload_hash=digest,
                    ),
                }
            )
        return {
            "actions": [
                item.model_dump(mode="json")
                for item in replace_workflow_action(state, action)
            ],
            "current_action_id": action.proposal.action_id,
            "status": (
                Stage3WorkflowStatus.WAITING_FOR_APPROVAL.value
                if action.status is ActionStatus.WAITING_FOR_APPROVAL
                else Stage3WorkflowStatus.APPROVED.value
            ),
            "audit": _audit(
                state,
                event_type="action_selected",
                status=action.status.value,
                action_id=action.proposal.action_id,
                payload_hash_value=payload_hash(action.proposal),
            ),
        }

    if state.actions and all(
        item.status is ActionStatus.COMPLETED for item in state.actions
    ):
        status = Stage3WorkflowStatus.COMPLETED
    elif any(item.status is ActionStatus.UNKNOWN for item in state.actions):
        status = Stage3WorkflowStatus.UNKNOWN
    elif any(item.status is ActionStatus.FAILED for item in state.actions):
        status = Stage3WorkflowStatus.FAILED
    elif any(item.status is ActionStatus.REJECTED for item in state.actions):
        status = Stage3WorkflowStatus.REJECTED
    else:
        status = Stage3WorkflowStatus.FAILED
    return {
        "current_action_id": None,
        "status": status.value,
        "audit": _audit(
            state,
            event_type="workflow_terminal",
            status=status.value,
            error_code=("dependency_blocked" if status is Stage3WorkflowStatus.FAILED else None),
        ),
    }


def _route_after_select(
    graph_state: EmailActionGraphState,
) -> Literal["approval_interrupt", "claim_execution", "execute_write", "finalize"]:
    state = _state(graph_state)
    if state.current_action_id is None:
        return "finalize"
    action = workflow_action_for(state, state.current_action_id)
    if action.status is ActionStatus.WAITING_FOR_APPROVAL:
        return "approval_interrupt"
    if action.status is ActionStatus.APPROVED:
        return "claim_execution"
    if action.status is ActionStatus.EXECUTION_CLAIMED:
        return "execute_write"
    return "finalize"


def _approval_interrupt_node(
    graph_state: EmailActionGraphState,
) -> EmailActionGraphState:
    state = _state(graph_state)
    action_id = state.current_action_id
    if action_id is None:
        raise InvalidTransitionError("approval interrupt has no current action")
    action = workflow_action_for(state, action_id)
    approval = action.approval
    if (
        action.status is not ActionStatus.WAITING_FOR_APPROVAL
        or approval is None
        or approval.status is not ApprovalStatus.PENDING
    ):
        raise ApprovalError("current action is not waiting for approval")

    resumed = interrupt(
        {
            "kind": "approval_required",
            "thread_id": state.thread_id,
            "action": action.proposal.model_dump(mode="json"),
            "revision": approval.revision,
            "payload_hash": approval.payload_hash,
        }
    )
    decision = ApprovalDecision.model_validate(resumed)
    if decision.expected_revision != approval.revision:
        raise ApprovalError("approval revision is stale")

    if decision.decision in {"edit", "clarify"}:
        edited = ActionProposal(
            action_id=action.proposal.action_id,
            tool_name=action.proposal.tool_name,
            parameters=decision.parameters or {},
        )
        digest = payload_hash(edited)
        replacement = WorkflowAction(
            proposal=edited,
            status=ActionStatus.WAITING_FOR_APPROVAL,
            approval=ApprovalRecord(
                action_id=edited.action_id,
                revision=approval.revision + 1,
                status=ApprovalStatus.PENDING,
                payload_hash=digest,
            ),
        )
        workflow_status = Stage3WorkflowStatus.WAITING_FOR_APPROVAL
        event_status = "clarified" if decision.decision == "clarify" else "edited"
    elif decision.decision == "reject":
        replacement = action.model_copy(
            update={
                "status": ActionStatus.REJECTED,
                "approval": ApprovalRecord(
                    action_id=action_id,
                    revision=approval.revision,
                    status=ApprovalStatus.REJECTED,
                    payload_hash=approval.payload_hash,
                ),
            }
        )
        workflow_status = Stage3WorkflowStatus.REJECTED
        event_status = "rejected"
    else:
        current_digest = payload_hash(action.proposal)
        if current_digest != approval.payload_hash:
            raise ApprovalError("proposal changed after approval was requested")
        replacement = action.model_copy(
            update={
                "status": ActionStatus.APPROVED,
                "approval": ApprovalRecord(
                    action_id=action_id,
                    revision=approval.revision,
                    status=ApprovalStatus.APPROVED,
                    payload_hash=current_digest,
                    approved_payload_hash=current_digest,
                ),
            }
        )
        workflow_status = Stage3WorkflowStatus.APPROVED
        event_status = "approved"

    return {
        "actions": [
            item.model_dump(mode="json")
            for item in replace_workflow_action(state, replacement)
        ],
        "status": workflow_status.value,
        "audit": _audit(
            state,
            event_type="approval_decided",
            status=event_status,
            action_id=action_id,
            payload_hash_value=payload_hash(replacement.proposal),
        ),
    }


def _route_after_approval(
    graph_state: EmailActionGraphState,
) -> Literal["approval_interrupt", "claim_execution", "finalize"]:
    state = _state(graph_state)
    if state.status is Stage3WorkflowStatus.WAITING_FOR_APPROVAL:
        return "approval_interrupt"
    if state.status is Stage3WorkflowStatus.APPROVED:
        return "claim_execution"
    return "finalize"


def _mark_action(
    state: WorkflowState,
    replacement: WorkflowAction,
    *,
    workflow_status: Stage3WorkflowStatus,
    event_type: str,
    event_status: str,
    idempotency_key: str,
) -> EmailActionGraphState:
    return {
        "actions": [
            item.model_dump(mode="json")
            for item in replace_workflow_action(state, replacement)
        ],
        "status": workflow_status.value,
        "audit": _audit(
            state,
            event_type=event_type,
            status=event_status,
            action_id=replacement.proposal.action_id,
            payload_hash_value=payload_hash(replacement.proposal),
            idempotency_key=idempotency_key,
            error_code=replacement.error_code,
        ),
    }


def build_email_action_graph(
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    store: BaseStore | None = None,
    execution_ledger: ExecutionLedger | None = None,
    write_executor: WriteExecutor | None = None,
):
    """Compile the single-source EmailActionAgent workflow."""

    ledger = execution_ledger or InMemoryExecutionLedger()

    async def claim_execution_node(
        graph_state: EmailActionGraphState,
    ) -> EmailActionGraphState:
        state = _state(graph_state)
        action_id = state.current_action_id
        if action_id is None:
            raise InvalidTransitionError("execution claim has no current action")
        permit = authorize_execution(state, action_id)
        outcome = await ledger.claim(permit)
        action = workflow_action_for(state, action_id)
        if outcome is ExecutionClaimOutcome.CLAIMED:
            replacement = action.model_copy(
                update={"status": ActionStatus.EXECUTION_CLAIMED}
            )
            return _mark_action(
                state,
                replacement,
                workflow_status=Stage3WorkflowStatus.EXECUTION_CLAIMED,
                event_type="execution_claimed",
                event_status="claimed",
                idempotency_key=permit.idempotency_key,
            )
        if outcome is ExecutionClaimOutcome.ALREADY_SUCCEEDED:
            replacement = action.model_copy(update={"status": ActionStatus.COMPLETED})
            completed = list(dict.fromkeys([*state.completed_action_ids, action_id]))
            update = _mark_action(
                state,
                replacement,
                workflow_status=Stage3WorkflowStatus.ACTION_REQUIRED,
                event_type="execution_recovered",
                event_status="already_succeeded",
                idempotency_key=permit.idempotency_key,
            )
            update["completed_action_ids"] = completed
            update["current_action_id"] = None
            return update
        replacement = action.model_copy(
            update={
                "status": ActionStatus.UNKNOWN,
                "error_code": "execution_requires_reconciliation",
            }
        )
        return _mark_action(
            state,
            replacement,
            workflow_status=Stage3WorkflowStatus.UNKNOWN,
            event_type="execution_claim_blocked",
            event_status="unknown",
            idempotency_key=permit.idempotency_key,
        )

    def route_after_claim(
        graph_state: EmailActionGraphState,
    ) -> Literal["execute_write", "select_next_action", "finalize"]:
        state = _state(graph_state)
        if state.status is Stage3WorkflowStatus.EXECUTION_CLAIMED:
            return "execute_write"
        if state.status is Stage3WorkflowStatus.ACTION_REQUIRED:
            return "select_next_action"
        return "finalize"

    async def execute_write_node(
        graph_state: EmailActionGraphState,
    ) -> EmailActionGraphState:
        state = _state(graph_state)
        action_id = state.current_action_id
        if action_id is None:
            raise InvalidTransitionError("write execution has no current action")
        permit = authorize_execution(state, action_id)
        start_outcome = await ledger.begin_execution(permit)
        if start_outcome is ExecutionStartOutcome.ALREADY_SUCCEEDED:
            action = workflow_action_for(state, action_id)
            replacement = action.model_copy(update={"status": ActionStatus.COMPLETED})
            completed = list(dict.fromkeys([*state.completed_action_ids, action_id]))
            update = _mark_action(
                state,
                replacement,
                workflow_status=Stage3WorkflowStatus.ACTION_REQUIRED,
                event_type="execution_recovered",
                event_status="already_succeeded",
                idempotency_key=permit.idempotency_key,
            )
            update["completed_action_ids"] = completed
            update["current_action_id"] = None
            return update
        if start_outcome is ExecutionStartOutcome.BLOCKED_UNKNOWN:
            action = workflow_action_for(state, action_id)
            replacement = action.model_copy(
                update={
                    "status": ActionStatus.UNKNOWN,
                    "error_code": "execution_replay_requires_reconciliation",
                }
            )
            return _mark_action(
                state,
                replacement,
                workflow_status=Stage3WorkflowStatus.UNKNOWN,
                event_type="execution_replay_blocked",
                event_status="unknown",
                idempotency_key=permit.idempotency_key,
            )
        if write_executor is None:
            result = ExecutionResult(
                status="unknown",
                error_code="write_executor_not_configured",
            )
        else:
            try:
                result = await write_executor.execute(permit)
            except Exception:  # noqa: BLE001 - provider exceptions become unknown
                result = ExecutionResult(
                    status="unknown",
                    error_code="write_executor_exception",
                )
        await ledger.complete(permit, result)
        action = workflow_action_for(state, action_id)
        if result.status == "succeeded":
            replacement = action.model_copy(update={"status": ActionStatus.COMPLETED})
            completed = list(dict.fromkeys([*state.completed_action_ids, action_id]))
            update = _mark_action(
                state,
                replacement,
                workflow_status=Stage3WorkflowStatus.ACTION_REQUIRED,
                event_type="execution_result",
                event_status="succeeded",
                idempotency_key=permit.idempotency_key,
            )
            update["completed_action_ids"] = completed
            update["current_action_id"] = None
            return update
        action_status = (
            ActionStatus.FAILED if result.status == "failed" else ActionStatus.UNKNOWN
        )
        workflow_status = (
            Stage3WorkflowStatus.FAILED
            if result.status == "failed"
            else Stage3WorkflowStatus.UNKNOWN
        )
        replacement = action.model_copy(
            update={"status": action_status, "error_code": result.error_code}
        )
        return _mark_action(
            state,
            replacement,
            workflow_status=workflow_status,
            event_type="execution_result",
            event_status=result.status,
            idempotency_key=permit.idempotency_key,
        )

    def route_after_execute(
        graph_state: EmailActionGraphState,
    ) -> Literal["select_next_action", "finalize"]:
        state = _state(graph_state)
        if state.status is Stage3WorkflowStatus.ACTION_REQUIRED:
            return "select_next_action"
        return "finalize"

    def finalize_node(
        graph_state: EmailActionGraphState,
    ) -> EmailActionGraphState:
        state = _state(graph_state)
        return {"status": state.status.value}

    builder: StateGraph[
        EmailActionGraphState,
        None,
        EmailActionGraphState,
        EmailActionGraphState,
    ] = StateGraph(EmailActionGraphState)
    node_input = EmailActionGraphState
    builder.add_node(
        "validate_start",
        cast(Any, _validate_start_node),
        input_schema=node_input,
    )
    builder.add_node(
        "select_next_action",
        cast(Any, _select_next_action_node),
        input_schema=node_input,
    )
    builder.add_node(
        "approval_interrupt",
        cast(Any, _approval_interrupt_node),
        input_schema=node_input,
    )
    builder.add_node(
        "claim_execution",
        cast(Any, claim_execution_node),
        input_schema=node_input,
    )
    builder.add_node(
        "execute_write",
        cast(Any, execute_write_node),
        input_schema=node_input,
    )
    builder.add_node("finalize", cast(Any, finalize_node), input_schema=node_input)

    builder.add_edge(START, "validate_start")
    builder.add_conditional_edges("validate_start", _route_after_start)
    builder.add_conditional_edges("select_next_action", _route_after_select)
    builder.add_conditional_edges("approval_interrupt", _route_after_approval)
    builder.add_conditional_edges("claim_execution", route_after_claim)
    builder.add_conditional_edges("execute_write", route_after_execute)
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer, store=store)
