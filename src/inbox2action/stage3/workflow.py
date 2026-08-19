from __future__ import annotations

from inbox2action.evaluation.policy_v3 import ParameterResolutionStatus
from inbox2action.llm.models import TriageDecision
from inbox2action.stage3.contracts import (
    ActionStatus,
    ApprovalStatus,
    AuditEvent,
    EmailEnvelope,
    ExecutionPermit,
    Stage2PlanningBundle,
    Stage3WorkflowStatus,
    WorkflowAction,
    WorkflowState,
    action_idempotency_key,
    payload_hash,
    workflow_thread_id,
)
from inbox2action.stage3.normalization import normalize_email


class Stage3WorkflowError(RuntimeError):
    """Base class for deterministic workflow contract failures."""


class InvalidTransitionError(Stage3WorkflowError):
    """The requested graph transition is not valid for current state."""


class ApprovalError(Stage3WorkflowError):
    """Approval is missing, stale, rejected, or bound to another payload."""


class DuplicateExecutionError(Stage3WorkflowError):
    """The action has already completed under the same workflow."""


class ActionDependencyError(Stage3WorkflowError):
    """An action was selected before all reviewed dependencies completed."""


class ParameterResolutionError(Stage3WorkflowError):
    """A required ActionPlan parameter is unresolved."""


def prepare_workflow_state(
    envelope: EmailEnvelope,
    planning: Stage2PlanningBundle,
) -> WorkflowState:
    """Normalize provider input before constructing durable LangGraph state."""

    normalized = normalize_email(envelope)
    thread_id = workflow_thread_id(envelope.account_id, envelope.message_id)
    if planning.triage.decision is TriageDecision.ACTION_REQUIRED:
        status = Stage3WorkflowStatus.ACTION_REQUIRED
    elif planning.triage.decision is TriageDecision.NOTIFY:
        status = Stage3WorkflowStatus.COMPLETED_NOTIFY
    else:
        status = Stage3WorkflowStatus.COMPLETED_IGNORE
    return WorkflowState(
        thread_id=thread_id,
        normalized_email=normalized,
        triage=planning.triage,
        status=status,
        action_plan=planning.action_plan,
        actions=[WorkflowAction(proposal=proposal) for proposal in planning.proposals],
        completed_action_ids=list(planning.precompleted_action_ids),
        audit=[AuditEvent(event_type="email_prepared", status=status.value)],
    )


def authorize_execution(
    state: WorkflowState,
    action_id: str,
) -> ExecutionPermit:
    """Central execution boundary for approval, parameters, DAG, and idempotency."""

    return _authorize_permit(
        state,
        action_id,
        allowed_statuses={ActionStatus.APPROVED, ActionStatus.EXECUTION_CLAIMED},
    )


def authorize_reconciliation(
    state: WorkflowState,
    action_id: str,
) -> ExecutionPermit:
    """Authorize readonly recovery of one previously UNKNOWN approved action."""

    return _authorize_permit(
        state,
        action_id,
        allowed_statuses={ActionStatus.UNKNOWN},
    )


def _authorize_permit(
    state: WorkflowState,
    action_id: str,
    *,
    allowed_statuses: set[ActionStatus],
) -> ExecutionPermit:
    """Share permit validation while keeping write and recovery entry points distinct."""

    workflow_action = workflow_action_for(state, action_id)
    if workflow_action.status is ActionStatus.COMPLETED:
        raise DuplicateExecutionError("action is already completed")
    if workflow_action.status not in allowed_statuses:
        raise ApprovalError("action is not approved for this operation")
    approval = workflow_action.approval
    if approval is None or approval.status is not ApprovalStatus.APPROVED:
        raise ApprovalError("approved human decision is required before execution")

    action_plan = state.action_plan
    if action_plan is None:
        raise InvalidTransitionError("action-required workflow has no ActionPlanV3")
    try:
        plan_action = action_plan.action(action_id)
    except KeyError as exc:
        raise InvalidTransitionError("proposal is not present in ActionPlanV3") from exc
    proposal = workflow_action.proposal
    if plan_action.tool_name != proposal.tool_name:
        raise InvalidTransitionError("proposal Tool differs from ActionPlanV3")
    if not set(plan_action.depends_on).issubset(state.completed_action_ids):
        raise ActionDependencyError("ActionPlanV3 dependencies are incomplete")
    resolutions = plan_action.resolution_map()
    if any(
        resolutions.get(parameter) is not ParameterResolutionStatus.RESOLVED
        for parameter in plan_action.required_parameters
    ):
        raise ParameterResolutionError("required ActionPlanV3 parameters are unresolved")

    digest = payload_hash(proposal)
    if approval.payload_hash != digest or approval.approved_payload_hash != digest:
        raise ApprovalError("approved payload hash does not match current proposal")
    key = action_idempotency_key(
        state.normalized_email.account_id,
        state.normalized_email.message_id,
        proposal,
    )
    return ExecutionPermit(
        thread_id=state.thread_id,
        action_id=action_id,
        action=proposal,
        approved_payload_hash=digest,
        idempotency_key=key,
    )


def workflow_action_for(state: WorkflowState, action_id: str) -> WorkflowAction:
    for action in state.actions:
        if action.proposal.action_id == action_id:
            return action
    raise InvalidTransitionError("workflow action does not exist")


def replace_workflow_action(
    state: WorkflowState,
    replacement: WorkflowAction,
) -> list[WorkflowAction]:
    action_id = replacement.proposal.action_id
    if not any(item.proposal.action_id == action_id for item in state.actions):
        raise InvalidTransitionError("replacement action does not exist")
    return [
        replacement if item.proposal.action_id == action_id else item
        for item in state.actions
    ]
