from __future__ import annotations

from typing import Any, Literal

from langgraph.types import Command

from inbox2action.stage3.contracts import (
    ActionProposal,
    ApprovalDecision,
    Stage3WorkflowStatus,
    WorkflowState,
)
from inbox2action.stage3.workflow import ApprovalError
from inbox2action.stage6.index import WorkflowIndex


class ApprovalServiceError(RuntimeError):
    """Safe application-layer error for approval clients."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


ApprovalOperation = Literal["approve", "reject", "edit", "clarify"]


class ApprovalService:
    """Thin application layer over the existing LangGraph approval interrupt."""

    def __init__(self, graph: Any, index: WorkflowIndex) -> None:
        self._graph = graph
        self._index = index

    async def list_pending(self) -> list[dict[str, object]]:
        views: list[dict[str, object]] = []
        for entry in await self._index.list_pending():
            try:
                view = await self.get_workflow(entry.thread_id)
            except ApprovalServiceError:
                continue
            if view["status"] == Stage3WorkflowStatus.WAITING_FOR_APPROVAL.value:
                views.append(view)
        return views

    async def get_workflow(self, thread_id: str) -> dict[str, object]:
        state = await self._load_state(thread_id)
        return _public_view(state)

    async def decide(
        self,
        thread_id: str,
        *,
        operation: ApprovalOperation,
        expected_revision: int,
        action_id: str,
        parameters: dict[str, object] | None = None,
    ) -> dict[str, object]:
        state = await self._load_state(thread_id)
        if state.current_action_id != action_id:
            raise ApprovalServiceError("stale_action")
        if state.status is not Stage3WorkflowStatus.WAITING_FOR_APPROVAL:
            raise ApprovalServiceError("workflow_not_waiting")
        current_action = next(
            (
                action
                for action in state.actions
                if action.proposal.action_id == action_id
            ),
            None,
        )
        if (
            current_action is None
            or current_action.approval is None
            or expected_revision != current_action.approval.revision
        ):
            raise ApprovalServiceError("stale_approval")
        try:
            decision = ApprovalDecision(
                decision=operation,
                expected_revision=expected_revision,
                parameters=parameters,
            )
        except ValueError as exc:
            raise ApprovalServiceError("invalid_approval") from exc

        if decision.decision in {"edit", "clarify"}:
            try:
                ActionProposal(
                    action_id=current_action.proposal.action_id,
                    tool_name=current_action.proposal.tool_name,
                    parameters=decision.parameters or {},
                )
            except ValueError as exc:
                raise ApprovalServiceError("invalid_approval") from exc

        try:
            result = await self._graph.ainvoke(
                Command(resume=decision.model_dump(mode="json")),
                {"configurable": {"thread_id": thread_id}},
            )
        except ApprovalError as exc:
            raise ApprovalServiceError("stale_approval") from exc

        status = _graph_status(result)
        await self._index.set_status(thread_id, status)
        return await self.get_workflow(thread_id)

    async def _load_state(self, thread_id: str) -> WorkflowState:
        try:
            snapshot = await self._graph.aget_state(
                {"configurable": {"thread_id": thread_id}}
            )
            values = getattr(snapshot, "values", None)
            if not isinstance(values, dict) or not values:
                raise ApprovalServiceError("workflow_not_found")
            return WorkflowState.model_validate(values)
        except ApprovalServiceError:
            raise
        except Exception as exc:
            raise ApprovalServiceError("workflow_not_found") from exc

def _graph_status(output: dict[str, object]) -> str:
    if output.get("__interrupt__"):
        return "waiting_for_approval"
    value = output.get("status")
    return value if isinstance(value, str) else "unknown"


def _public_view(state: WorkflowState) -> dict[str, object]:
    current_action = next(
        (
            action
            for action in state.actions
            if action.proposal.action_id == state.current_action_id
        ),
        None,
    )
    return {
        "thread_id": state.thread_id,
        "status": state.status.value,
        "email": {
            "account_id": state.normalized_email.account_id,
            "message_id": state.normalized_email.message_id,
            "provider_thread_id": state.normalized_email.provider_thread_id,
            "from_address": state.normalized_email.from_address,
            "reply_to": state.normalized_email.reply_to,
            "subject": state.normalized_email.subject,
            "received_at": state.normalized_email.received_at,
            "sanitized_body": state.normalized_email.sanitized_body,
        },
        "triage": state.triage.model_dump(mode="json"),
        "action_plan": (
            state.action_plan.model_dump(mode="json")
            if state.action_plan is not None
            else None
        ),
        "actions": [action.model_dump(mode="json") for action in state.actions],
        "current_action_id": state.current_action_id,
        "approval_revision": (
            current_action.approval.revision
            if current_action is not None and current_action.approval is not None
            else None
        ),
        "audit": [event.model_dump(mode="json") for event in state.audit],
    }
