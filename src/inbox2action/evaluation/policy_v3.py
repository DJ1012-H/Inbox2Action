"""Versioned deterministic action-policy contracts for stage-two remediation."""

from __future__ import annotations

import json
from collections.abc import Sequence
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class ParameterResolutionStatus(str, Enum):
    RESOLVED = "RESOLVED"
    MISSING_REQUIRED = "MISSING_REQUIRED"
    AMBIGUOUS = "AMBIGUOUS"
    CONFLICTING = "CONFLICTING"
    NOT_REQUIRED = "NOT_REQUIRED"


class ParameterResolutionV3(BaseModel):
    """A non-secret business-resolution result for one action parameter."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    field_name: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
    )
    status: ParameterResolutionStatus
    source: str | None = Field(default=None, max_length=128)


class ActionNodeV3(BaseModel):
    """One authorized action and its deterministic prerequisites."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    action_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    )
    tool_name: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
    )
    depends_on: tuple[str, ...] = ()
    required_parameters: tuple[str, ...] = ()
    parameter_resolutions: tuple[ParameterResolutionV3, ...] = ()
    requires_approval: bool = False

    @model_validator(mode="after")
    def validate_local_contract(self) -> ActionNodeV3:
        if self.action_id in self.depends_on:
            raise ValueError("action cannot depend on itself")
        if len(self.depends_on) != len(set(self.depends_on)):
            raise ValueError("depends_on must not contain duplicates")
        if len(self.required_parameters) != len(set(self.required_parameters)):
            raise ValueError("required_parameters must not contain duplicates")
        resolution_names = [
            resolution.field_name for resolution in self.parameter_resolutions
        ]
        if len(resolution_names) != len(set(resolution_names)):
            raise ValueError("parameter_resolutions must not contain duplicates")
        return self

    def resolution_map(self) -> dict[str, ParameterResolutionStatus]:
        return {
            resolution.field_name: resolution.status
            for resolution in self.parameter_resolutions
        }


class ActionPlanV3(BaseModel):
    """A bounded acyclic action graph consumed by the execution policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    plan_version: str = "stage2-action-plan-v3"
    actions: tuple[ActionNodeV3, ...] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_graph(self) -> ActionPlanV3:
        action_ids = [action.action_id for action in self.actions]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("action_id values must be unique")
        known = set(action_ids)
        for action in self.actions:
            unknown = set(action.depends_on).difference(known)
            if unknown:
                raise ValueError("action has an unknown dependency")
        self._assert_acyclic()
        return self

    def _assert_acyclic(self) -> None:
        dependencies = {
            action.action_id: set(action.depends_on) for action in self.actions
        }
        temporary: set[str] = set()
        permanent: set[str] = set()

        def visit(action_id: str) -> None:
            if action_id in permanent:
                return
            if action_id in temporary:
                raise ValueError("action dependency cycle detected")
            temporary.add(action_id)
            for dependency in dependencies[action_id]:
                visit(dependency)
            temporary.remove(action_id)
            permanent.add(action_id)

        for action_id in dependencies:
            visit(action_id)

    def action(self, action_id: str) -> ActionNodeV3:
        for action in self.actions:
            if action.action_id == action_id:
                return action
        raise KeyError(action_id)

    def actions_for_tool(self, tool_name: str) -> tuple[ActionNodeV3, ...]:
        return tuple(action for action in self.actions if action.tool_name == tool_name)

    def exposed_tool_names(self) -> frozenset[str]:
        return frozenset(action.tool_name for action in self.actions)

    def is_valid_tool_sequence(self, tool_names: Sequence[str]) -> bool:
        if len(tool_names) != len(self.actions):
            return False
        actions_by_tool: dict[str, ActionNodeV3] = {}
        for action in self.actions:
            if action.tool_name in actions_by_tool:
                return False
            actions_by_tool[action.tool_name] = action
        if set(tool_names) != set(actions_by_tool):
            return False
        completed: set[str] = set()
        for tool_name in tool_names:
            action = actions_by_tool[tool_name]
            if not set(action.depends_on).issubset(completed):
                return False
            completed.add(action.action_id)
        return True


class CaseExecutionPolicyV3(BaseModel):
    """Independently reviewed runtime authorization, separate from Gold labels."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_version: Literal["stage2-case-policy-v3"] = "stage2-case-policy-v3"
    case_id: str = Field(
        min_length=3,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    )
    review_status: Literal["draft", "approved"] = "draft"
    policy_source: Literal["reviewed_policy", "diagnostic_only"]
    action_plan: ActionPlanV3
    approved_action_ids: frozenset[str] = frozenset()

    @model_validator(mode="after")
    def validate_approvals(self) -> CaseExecutionPolicyV3:
        known = {action.action_id for action in self.action_plan.actions}
        if not self.approved_action_ids.issubset(known):
            raise ValueError("approved_action_ids contains an unknown action")
        done_actions = [
            action
            for action in self.action_plan.actions
            if action.tool_name == "done"
        ]
        if len(done_actions) != 1:
            raise ValueError("case policy requires exactly one done action")
        done_action = done_actions[0]
        dependencies = {
            action.action_id: set(action.depends_on)
            for action in self.action_plan.actions
        }
        ancestors: set[str] = set()
        pending = list(dependencies[done_action.action_id])
        while pending:
            dependency = pending.pop()
            if dependency in ancestors:
                continue
            ancestors.add(dependency)
            pending.extend(dependencies[dependency])
        required_ancestors = known.difference({done_action.action_id})
        if ancestors != required_ancestors:
            raise ValueError("done action must depend on all other actions")
        return self

    @property
    def eligible_for_formal_acceptance(self) -> bool:
        return (
            self.review_status == "approved"
            and self.policy_source == "reviewed_policy"
        )


def load_case_execution_policies_v3(
    path: Path,
) -> dict[str, CaseExecutionPolicyV3]:
    policies: dict[str, CaseExecutionPolicyV3] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            if len(policies) >= 60:
                raise ValueError(f"too many case policies at line {line_number}")
            try:
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    raise TypeError("case policy must be a JSON object")
                policy = CaseExecutionPolicyV3.model_validate(payload)
            except (json.JSONDecodeError, TypeError, ValidationError, ValueError) as exc:
                raise ValueError(
                    f"invalid case policy at line {line_number}"
                ) from exc
            if policy.case_id in policies:
                raise ValueError(
                    f"duplicate case policy at line {line_number}"
                )
            policies[policy.case_id] = policy
    return policies


def action_plan_from_allowed_sequences_v3(
    allowed_sequences: Sequence[Sequence[str]],
    *,
    parameter_resolutions: dict[str, tuple[ParameterResolutionV3, ...]] | None = None,
    required_parameters: dict[str, tuple[str, ...]] | None = None,
    approval_required_tools: frozenset[str] = frozenset(),
) -> ActionPlanV3:
    """Convert reviewed equivalent sequences into their common partial order."""

    if not allowed_sequences:
        raise ValueError("at least one allowed sequence is required")
    normalized = tuple(tuple(sequence) for sequence in allowed_sequences)
    first = normalized[0]
    if not first or len(first) != len(set(first)):
        raise ValueError("allowed sequences must contain unique tools")
    expected_tools = set(first)
    if any(set(sequence) != expected_tools for sequence in normalized):
        raise ValueError("all allowed sequences must contain the same tools")
    if any(len(sequence) != len(set(sequence)) for sequence in normalized):
        raise ValueError("allowed sequences must contain unique tools")

    resolutions = parameter_resolutions or {}
    required = required_parameters or {}
    indexes = [
        {tool_name: index for index, tool_name in enumerate(sequence)}
        for sequence in normalized
    ]
    actions: list[ActionNodeV3] = []
    for tool_name in first:
        dependencies = tuple(
            candidate
            for candidate in first
            if candidate != tool_name
            and all(index[candidate] < index[tool_name] for index in indexes)
        )
        actions.append(
            ActionNodeV3(
                action_id=f"action-{len(actions) + 1}-{tool_name}",
                tool_name=tool_name,
                depends_on=tuple(
                    f"action-{first.index(dependency) + 1}-{dependency}"
                    for dependency in dependencies
                ),
                required_parameters=required.get(tool_name, ()),
                parameter_resolutions=resolutions.get(tool_name, ()),
                requires_approval=tool_name in approval_required_tools,
            )
        )
    return ActionPlanV3(actions=tuple(actions))
