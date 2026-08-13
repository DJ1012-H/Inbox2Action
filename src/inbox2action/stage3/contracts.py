from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from inbox2action.evaluation.policy_v3 import (
    ActionPlanV3,
    ParameterResolutionStatus,
)
from inbox2action.evaluation.triage_v3 import TriageResultV3
from inbox2action.tools.schemas import validate_write_tool_parameters

WriteToolName = Literal[
    "save_reply_draft",
    "save_task_proposal",
    "create_clickup_task",
    "create_calendar_event",
]
WRITE_TOOL_NAMES = frozenset(
    {
        "save_reply_draft",
        "save_task_proposal",
        "create_clickup_task",
        "create_calendar_event",
    }
)


class Stage3WorkflowStatus(str, Enum):
    TRIAGED = "triaged"
    ACTION_REQUIRED = "action_required"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    APPROVED = "approved"
    EXECUTION_CLAIMED = "execution_claimed"
    COMPLETED = "completed"
    COMPLETED_IGNORE = "completed_ignore"
    COMPLETED_NOTIFY = "completed_notify"
    REJECTED = "rejected"
    FAILED = "failed"
    UNKNOWN = "unknown"


class ActionStatus(str, Enum):
    PROPOSED = "proposed"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    APPROVED = "approved"
    EXECUTION_CLAIMED = "execution_claimed"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"
    UNKNOWN = "unknown"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


def canonical_json(value: Mapping[str, object]) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("payload must contain only JSON-compatible values") from exc


class EmailEnvelope(BaseModel):
    """Provider input that is normalized before entering the durable graph."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    account_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:@/-]+$",
    )
    message_id: str = Field(min_length=1, max_length=256)
    provider_thread_id: str | None = Field(default=None, max_length=256)
    from_address: str | None = Field(default=None, max_length=320)
    reply_to: str | None = Field(default=None, max_length=320)
    subject: str = Field(max_length=200)
    body: str = Field(min_length=1, max_length=50_000)
    html: str | None = Field(default=None, max_length=100_000)
    received_at: str | None = Field(default=None, max_length=64)


class NormalizedEmail(BaseModel):
    """The only email representation allowed into durable graph state."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    account_id: str = Field(min_length=1, max_length=128)
    message_id: str = Field(min_length=1, max_length=256)
    provider_thread_id: str | None = Field(default=None, max_length=256)
    from_address: str | None = Field(default=None, max_length=320)
    reply_to: str | None = Field(default=None, max_length=320)
    received_at: str | None = Field(default=None, max_length=64)
    subject: str = Field(min_length=1, max_length=200)
    sanitized_body: str = Field(min_length=1, max_length=12_020)
    source_body_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    redaction_count: int = Field(ge=0)
    removed_tracking_parameters: int = Field(ge=0)
    contains_injection_signals: bool = False


class ActionProposal(BaseModel):
    """One schema-valid write proposal bound to a reviewed Stage 2 action."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )
    tool_name: WriteToolName
    parameters: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_and_normalize_parameters(self) -> ActionProposal:
        self.parameters = validate_write_tool_parameters(
            self.tool_name,
            self.parameters,
        )
        canonical_json(
            {
                "action_id": self.action_id,
                "action_type": self.tool_name,
                "parameters": self.parameters,
            }
        )
        return self


class ApprovalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(min_length=1, max_length=128)
    revision: int = Field(ge=1)
    status: ApprovalStatus
    payload_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    approved_payload_hash: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )

    @model_validator(mode="after")
    def validate_approval_hash(self) -> ApprovalRecord:
        if self.status is ApprovalStatus.APPROVED:
            if self.approved_payload_hash != self.payload_hash:
                raise ValueError("approved payload hash must match current payload")
        elif self.approved_payload_hash is not None:
            raise ValueError("pending or rejected approval cannot carry an approval hash")
        return self


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "edit", "reject"]
    expected_revision: int = Field(ge=1)
    parameters: dict[str, object] | None = None

    @model_validator(mode="after")
    def validate_edit_payload(self) -> ApprovalDecision:
        if self.decision == "edit" and self.parameters is None:
            raise ValueError("edit requires replacement parameters")
        if self.decision != "edit" and self.parameters is not None:
            raise ValueError("only edit may include replacement parameters")
        return self


class AuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str = Field(min_length=1, max_length=64)
    status: str = Field(min_length=1, max_length=32)
    action_id: str | None = Field(default=None, max_length=128)
    payload_hash: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    idempotency_key: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    error_code: str | None = Field(default=None, max_length=64)


class WorkflowAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal: ActionProposal
    status: ActionStatus = ActionStatus.PROPOSED
    approval: ApprovalRecord | None = None
    error_code: str | None = Field(default=None, max_length=64)


class Stage2PlanningBundle(BaseModel):
    """Validated handoff from the accepted Stage 2 planning contracts."""

    model_config = ConfigDict(extra="forbid")

    triage: TriageResultV3
    action_plan: ActionPlanV3 | None = None
    proposals: list[ActionProposal] = Field(default_factory=list, max_length=20)
    precompleted_action_ids: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_plan_handoff(self) -> Stage2PlanningBundle:
        if self.triage.decision.value != "ACTION_REQUIRED":
            if self.action_plan is not None or self.proposals:
                raise ValueError("non-action triage cannot carry an action plan")
            return self
        if self.action_plan is None:
            raise ValueError("action-required triage requires an ActionPlanV3")

        plan_actions = {action.action_id: action for action in self.action_plan.actions}
        if not set(self.precompleted_action_ids).issubset(plan_actions):
            raise ValueError("precompleted action is not present in the action plan")
        write_actions = {
            action.action_id: action
            for action in self.action_plan.actions
            if action.tool_name in WRITE_TOOL_NAMES
            and action.action_id not in self.precompleted_action_ids
        }
        proposals = {proposal.action_id: proposal for proposal in self.proposals}
        if len(proposals) != len(self.proposals):
            raise ValueError("proposal action_id values must be unique")
        if set(proposals) != set(write_actions):
            raise ValueError("proposals must match pending write actions exactly")
        for action_id, proposal in proposals.items():
            action = write_actions[action_id]
            if proposal.tool_name != action.tool_name:
                raise ValueError("proposal Tool does not match its ActionPlan node")
            if not action.requires_approval:
                raise ValueError("every write action must require approval")
            resolutions = action.resolution_map()
            if any(
                resolutions.get(parameter) is not ParameterResolutionStatus.RESOLVED
                for parameter in action.required_parameters
            ):
                raise ValueError("required ActionPlan parameters are unresolved")
        return self


class WorkflowState(BaseModel):
    """Single durable business state stored by the LangGraph checkpointer."""

    model_config = ConfigDict(extra="forbid")

    thread_id: str = Field(
        min_length=30,
        max_length=30,
        pattern=r"^email:[0-9a-f]{24}$",
    )
    normalized_email: NormalizedEmail
    triage: TriageResultV3
    status: Stage3WorkflowStatus
    action_plan: ActionPlanV3 | None = None
    actions: list[WorkflowAction] = Field(default_factory=list, max_length=20)
    completed_action_ids: list[str] = Field(default_factory=list, max_length=20)
    current_action_id: str | None = Field(default=None, max_length=128)
    audit: list[AuditEvent] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def validate_action_state(self) -> WorkflowState:
        action_ids = [item.proposal.action_id for item in self.actions]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("workflow action_id values must be unique")
        if self.current_action_id is not None and self.current_action_id not in action_ids:
            raise ValueError("current_action_id is not present in workflow actions")
        if not set(self.completed_action_ids).issubset(action_ids):
            plan_ids = (
                {action.action_id for action in self.action_plan.actions}
                if self.action_plan is not None
                else set()
            )
            if not set(self.completed_action_ids).issubset(plan_ids):
                raise ValueError("completed action is not present in the action plan")
        return self


class ExecutionPermit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    thread_id: str
    action_id: str
    action: ActionProposal
    approved_payload_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    idempotency_key: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )


class ExecutionResult(BaseModel):
    """Provider outcome; unknown means reconciliation is required."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["succeeded", "failed", "unknown"]
    error_code: str | None = Field(default=None, max_length=64)


def payload_hash(proposal: ActionProposal) -> str:
    payload = canonical_json(
        {
            "action_id": proposal.action_id,
            "action_type": proposal.tool_name,
            "parameters": proposal.parameters,
        }
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def action_idempotency_key(
    account_id: str,
    message_id: str,
    proposal: ActionProposal,
) -> str:
    payload = canonical_json(
        {
            "email_id": f"{account_id}:{message_id}",
            "action_type": proposal.tool_name,
            "normalized_payload": {
                "action_id": proposal.action_id,
                "parameters": proposal.parameters,
            },
        }
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def workflow_thread_id(account_id: str, message_id: str) -> str:
    digest = hashlib.sha256(f"{account_id}:{message_id}".encode()).hexdigest()
    return f"email:{digest[:24]}"
