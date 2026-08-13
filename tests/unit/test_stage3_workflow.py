import pytest
from pydantic import ValidationError

from inbox2action.evaluation.policy_v3 import (
    ActionNodeV3,
    ActionPlanV3,
    ParameterResolutionStatus,
    ParameterResolutionV3,
)
from inbox2action.evaluation.triage_v3 import TriageResultV3
from inbox2action.llm.models import TriageDecision
from inbox2action.stage3 import (
    ActionDependencyError,
    ActionProposal,
    ActionStatus,
    ApprovalRecord,
    EmailEnvelope,
    Stage2PlanningBundle,
    Stage3WorkflowStatus,
    WorkflowAction,
    authorize_execution,
    prepare_workflow_state,
)
from inbox2action.stage3.contracts import ApprovalStatus, payload_hash


def _triage(decision: TriageDecision) -> TriageResultV3:
    return TriageResultV3(
        decision=decision,
        reason="reviewed Stage 2 handoff",
        confidence=1.0,
        suspected_prompt_injection=False,
        security_reason=None,
        safe_to_plan_actions=True,
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


def _proposal(action_id: str = "draft-1") -> ActionProposal:
    return ActionProposal(
        action_id=action_id,
        tool_name="save_reply_draft",
        parameters={
            "recipient": "person@example.test",
            "subject": "Meeting confirmation",
            "body": "Received; I will confirm the time.",
        },
    )


def _plan(*, depends_on: tuple[str, ...] = ()) -> ActionPlanV3:
    prerequisites = tuple(
        ActionNodeV3(
            action_id=action_id,
            tool_name="get_current_time",
            requires_approval=False,
        )
        for action_id in depends_on
    )
    return ActionPlanV3(
        actions=(*prerequisites,
            ActionNodeV3(
                action_id="draft-1",
                tool_name="save_reply_draft",
                depends_on=depends_on,
                required_parameters=("subject", "body"),
                parameter_resolutions=_resolved("subject", "body"),
                requires_approval=True,
            ),
        )
    )


def _email() -> EmailEnvelope:
    return EmailEnvelope(
        account_id="test-account",
        message_id="message-001",
        from_address="person@example.test",
        subject="Please prepare a meeting",
        body="Please arrange the meeting tomorrow morning.",
    )


def test_prepare_state_normalizes_before_graph_and_uses_stage2_plan() -> None:
    state = prepare_workflow_state(
        _email(),
        Stage2PlanningBundle(
            triage=_triage(TriageDecision.ACTION_REQUIRED),
            action_plan=_plan(),
            proposals=[_proposal()],
        ),
    )

    payload = state.model_dump(mode="json")
    assert "envelope" not in payload
    assert "body" not in payload
    assert state.normalized_email.sanitized_body.startswith("Please arrange")
    assert state.action_plan is not None
    assert state.actions[0].proposal.action_id == "draft-1"


def test_tool_parameters_are_validated_before_approval() -> None:
    with pytest.raises(ValidationError):
        ActionProposal(
            action_id="invalid-draft",
            tool_name="save_reply_draft",
            parameters={"subject": "Missing body"},
        )


def test_central_authorization_rechecks_approval_hash_and_dependencies() -> None:
    state = prepare_workflow_state(
        _email(),
        Stage2PlanningBundle(
            triage=_triage(TriageDecision.ACTION_REQUIRED),
            action_plan=_plan(depends_on=("read-time",)),
            proposals=[_proposal()],
            precompleted_action_ids=["read-time"],
        ),
    )
    proposal = state.actions[0].proposal
    digest = payload_hash(proposal)
    approved = WorkflowAction(
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
    state = state.model_copy(
        update={
            "actions": [approved],
            "status": Stage3WorkflowStatus.APPROVED,
            "current_action_id": proposal.action_id,
        }
    )

    permit = authorize_execution(state, proposal.action_id)
    assert permit.approved_payload_hash == digest

    incomplete = state.model_copy(update={"completed_action_ids": []})
    with pytest.raises(ActionDependencyError):
        authorize_execution(incomplete, proposal.action_id)


def test_non_action_triage_cannot_smuggle_an_action_plan() -> None:
    with pytest.raises(ValidationError):
        Stage2PlanningBundle(
            triage=_triage(TriageDecision.IGNORE),
            action_plan=_plan(),
            proposals=[_proposal()],
        )
