"""Fail-closed action authorization layered over the frozen ToolRegistry."""

from __future__ import annotations

from dataclasses import dataclass

from inbox2action.evaluation.policy_v3 import (
    ActionNodeV3,
    ActionPlanV3,
    ParameterResolutionStatus,
)
from inbox2action.llm.models import ToolCall
from inbox2action.tools.mock_tools import MockToolRuntime, ToolObservation
from inbox2action.tools.policy import (
    ALLOWED_TOOL_NAMES,
    ToolError,
    UnknownToolError,
)
from inbox2action.tools.registry import ToolRegistry, ValidatedToolCall


class AuthorizationPolicyError(ToolError):
    """A known Tool failed the deterministic action policy."""


class UnauthorizedToolError(AuthorizationPolicyError):
    """The Tool is registered but no current action authorizes it."""


class AmbiguousActionBindingError(AuthorizationPolicyError):
    """A Tool call cannot be bound to exactly one pending action."""


class ParameterResolutionError(AuthorizationPolicyError):
    """A business-required parameter is unresolved or contradictory."""


class ApprovalRequiredError(AuthorizationPolicyError):
    """A write-capable action lacks recorded approval."""


class ActionDependencyError(AuthorizationPolicyError):
    """An action was attempted before all of its prerequisites completed."""


@dataclass(frozen=True)
class ToolSecurityCountersV3:
    total_tool_attempts: int
    authorized_tool_executions: int
    unauthorized_tool_attempts: int
    unauthorized_tool_executions: int
    unknown_tool_attempts: int
    unknown_tool_executions: int
    parameter_blocked_attempts: int
    approval_bypass_attempts: int
    dependency_blocked_attempts: int


class AuthorizedToolRegistryV3(ToolRegistry):
    """Bind each Tool call to one approved, dependency-ready Action node."""

    def __init__(
        self,
        runtime: MockToolRuntime | None = None,
        *,
        action_plan: ActionPlanV3,
        approved_action_ids: set[str] | frozenset[str] = frozenset(),
    ) -> None:
        super().__init__(runtime)
        known_action_ids = {action.action_id for action in action_plan.actions}
        unknown_approvals = set(approved_action_ids).difference(known_action_ids)
        if unknown_approvals:
            raise ValueError("approved_action_ids contains an unknown action")
        self._action_plan = action_plan
        self._approved_action_ids = frozenset(approved_action_ids)
        self._completed_action_ids: set[str] = set()
        self._call_bindings: dict[str, str] = {}
        self._total_attempts = 0
        self._authorized_executions = 0
        self._unauthorized_attempts = 0
        self._unknown_attempts = 0
        self._parameter_blocked_attempts = 0
        self._approval_bypass_attempts = 0
        self._dependency_blocked_attempts = 0

    @property
    def completed_action_ids(self) -> frozenset[str]:
        return frozenset(self._completed_action_ids)

    def openai_tools(self) -> list[dict[str, object]]:
        exposed = self._action_plan.exposed_tool_names()
        return [
            tool
            for tool in super().openai_tools()
            if tool["function"]["name"] in exposed  # type: ignore[index]
        ]

    def openai_tool_names(self) -> tuple[str, ...]:
        exposed = self._action_plan.exposed_tool_names()
        return tuple(name for name in super().openai_tool_names() if name in exposed)

    def validate_call(self, call: ToolCall) -> ValidatedToolCall:
        self._total_attempts += 1
        if call.name not in ALLOWED_TOOL_NAMES:
            self._unknown_attempts += 1
            raise UnknownToolError("Tool is not registered.")

        action = self._bind_pending_action(call.name)
        self._validate_parameter_resolution(action)
        if (
            action.requires_approval
            and action.action_id not in self._approved_action_ids
        ):
            self._approval_bypass_attempts += 1
            raise ApprovalRequiredError("Action requires approval.")
        if not set(action.depends_on).issubset(self._completed_action_ids):
            self._dependency_blocked_attempts += 1
            raise ActionDependencyError("Action dependencies are not complete.")

        validated = super().validate_call(call)
        self._call_bindings[call.id] = action.action_id
        return validated

    def execute_validated(
        self,
        validated: ValidatedToolCall,
        *,
        tool_call_id: str,
    ) -> ToolObservation:
        action_id = self._call_bindings.get(validated.call.id)
        if action_id is None:
            self._unauthorized_attempts += 1
            raise UnauthorizedToolError("Validated call has no action binding.")
        observation = super().execute_validated(
            validated,
            tool_call_id=tool_call_id,
        )
        self._completed_action_ids.add(action_id)
        self._authorized_executions += 1
        return observation

    def security_counters(self) -> ToolSecurityCountersV3:
        return ToolSecurityCountersV3(
            total_tool_attempts=self._total_attempts,
            authorized_tool_executions=self._authorized_executions,
            unauthorized_tool_attempts=self._unauthorized_attempts,
            unauthorized_tool_executions=0,
            unknown_tool_attempts=self._unknown_attempts,
            unknown_tool_executions=0,
            parameter_blocked_attempts=self._parameter_blocked_attempts,
            approval_bypass_attempts=self._approval_bypass_attempts,
            dependency_blocked_attempts=self._dependency_blocked_attempts,
        )

    def _bind_pending_action(self, tool_name: str) -> ActionNodeV3:
        candidates = tuple(
            action
            for action in self._action_plan.actions_for_tool(tool_name)
            if action.action_id not in self._completed_action_ids
            and action.action_id not in self._call_bindings.values()
        )
        if not candidates:
            self._unauthorized_attempts += 1
            raise UnauthorizedToolError("Tool is not authorized by the action plan.")
        if len(candidates) != 1:
            self._unauthorized_attempts += 1
            raise AmbiguousActionBindingError("Tool maps to multiple pending actions.")
        return candidates[0]

    def _validate_parameter_resolution(self, action: ActionNodeV3) -> None:
        resolutions = action.resolution_map()
        blocked_statuses = {
            ParameterResolutionStatus.MISSING_REQUIRED,
            ParameterResolutionStatus.AMBIGUOUS,
            ParameterResolutionStatus.CONFLICTING,
        }
        blocked = any(status in blocked_statuses for status in resolutions.values())
        required_unresolved = any(
            resolutions.get(parameter) is not ParameterResolutionStatus.RESOLVED
            for parameter in action.required_parameters
        )
        if blocked or required_unresolved:
            self._parameter_blocked_attempts += 1
            raise ParameterResolutionError("Action parameters are not resolved.")
