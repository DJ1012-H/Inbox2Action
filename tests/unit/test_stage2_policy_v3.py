from __future__ import annotations

import pytest
from pydantic import ValidationError

from inbox2action.evaluation.policy_v3 import (
    ActionNodeV3,
    ActionPlanV3,
    CaseExecutionPolicyV3,
    ParameterResolutionStatus,
    ParameterResolutionV3,
    action_plan_from_allowed_sequences_v3,
)
from inbox2action.llm.models import ToolCall
from inbox2action.tools.authorization_v3 import (
    ActionDependencyError,
    ApprovalRequiredError,
    AuthorizedToolRegistryV3,
    ParameterResolutionError,
    UnauthorizedToolError,
)
from inbox2action.tools.mock_tools import MockToolRuntime
from inbox2action.tools.policy import UnknownToolError


def _call(name: str, arguments: str, call_id: str = "call-1") -> ToolCall:
    return ToolCall(id=call_id, name=name, arguments=arguments)


def _resolution(
    field_name: str,
    status: ParameterResolutionStatus = ParameterResolutionStatus.RESOLVED,
) -> ParameterResolutionV3:
    return ParameterResolutionV3(field_name=field_name, status=status)


def _node(
    action_id: str,
    tool_name: str,
    *,
    depends_on: tuple[str, ...] = (),
    required_parameters: tuple[str, ...] = (),
    parameter_resolutions: tuple[ParameterResolutionV3, ...] = (),
    requires_approval: bool = False,
) -> ActionNodeV3:
    return ActionNodeV3(
        action_id=action_id,
        tool_name=tool_name,
        depends_on=depends_on,
        required_parameters=required_parameters,
        parameter_resolutions=parameter_resolutions,
        requires_approval=requires_approval,
    )


def test_action_plan_rejects_unknown_dependencies_and_cycles() -> None:
    with pytest.raises(ValidationError, match="unknown dependency"):
        ActionPlanV3(
            actions=(
                _node("reply", "save_reply_draft", depends_on=("missing",)),
            )
        )

    with pytest.raises(ValidationError, match="cycle"):
        ActionPlanV3(
            actions=(
                _node("reply", "save_reply_draft", depends_on=("task",)),
                _node("task", "save_task_proposal", depends_on=("reply",)),
            )
        )


def test_action_plan_accepts_only_dependency_valid_sequences() -> None:
    plan = ActionPlanV3(
        actions=(
            _node("reply", "save_reply_draft"),
            _node("task", "save_task_proposal", depends_on=("reply",)),
            _node("done", "done", depends_on=("task",)),
        )
    )

    assert plan.is_valid_tool_sequence(
        ("save_reply_draft", "save_task_proposal", "done")
    )
    assert not plan.is_valid_tool_sequence(
        ("save_task_proposal", "save_reply_draft", "done")
    )


def test_case_policy_requires_done_to_cover_every_planned_action() -> None:
    with pytest.raises(ValidationError, match="done action must depend"):
        CaseExecutionPolicyV3(
            case_id="case-001",
            review_status="approved",
            policy_source="reviewed_policy",
            action_plan=ActionPlanV3(
                actions=(
                    _node("reply", "save_reply_draft"),
                    _node("done", "done"),
                )
            ),
        )


def test_equivalent_reviewed_sequences_become_one_partial_order() -> None:
    plan = action_plan_from_allowed_sequences_v3(
        (
            ("save_reply_draft", "save_task_proposal", "done"),
            ("save_task_proposal", "save_reply_draft", "done"),
        )
    )

    assert plan.is_valid_tool_sequence(
        ("save_reply_draft", "save_task_proposal", "done")
    )
    assert plan.is_valid_tool_sequence(
        ("save_task_proposal", "save_reply_draft", "done")
    )


def test_unauthorized_known_tool_is_blocked_before_handler_execution() -> None:
    runtime = MockToolRuntime()
    registry = AuthorizedToolRegistryV3(
        runtime,
        action_plan=ActionPlanV3(actions=(_node("done", "done"),)),
    )

    with pytest.raises(UnauthorizedToolError):
        registry.execute(
            _call(
                "save_reply_draft",
                '{"recipient":"safe@example.invalid","subject":"s","body":"b"}',
            )
        )

    counters = registry.security_counters()
    assert counters.unauthorized_tool_attempts == 1
    assert counters.unauthorized_tool_executions == 0
    assert registry.execution_count("save_reply_draft") == 0
    assert runtime.proposals == []


def test_unknown_tool_attempt_is_distinct_from_unauthorized_known_tool() -> None:
    registry = AuthorizedToolRegistryV3(
        action_plan=ActionPlanV3(actions=(_node("done", "done"),))
    )

    with pytest.raises(UnknownToolError):
        registry.execute(_call("send_email", "{}"))

    counters = registry.security_counters()
    assert counters.unknown_tool_attempts == 1
    assert counters.unauthorized_tool_attempts == 0
    assert counters.unknown_tool_executions == 0


@pytest.mark.parametrize(
    "status",
    (
        ParameterResolutionStatus.MISSING_REQUIRED,
        ParameterResolutionStatus.AMBIGUOUS,
        ParameterResolutionStatus.CONFLICTING,
    ),
)
def test_unresolved_business_parameter_blocks_tool_before_execution(
    status: ParameterResolutionStatus,
) -> None:
    plan = ActionPlanV3(
        actions=(
            _node(
                "task",
                "save_task_proposal",
                required_parameters=("due_at",),
                parameter_resolutions=(_resolution("due_at", status),),
            ),
        )
    )
    registry = AuthorizedToolRegistryV3(action_plan=plan)

    with pytest.raises(ParameterResolutionError):
        registry.execute(
            _call(
                "save_task_proposal",
                '{"title":"t","description":"d","due_at":null,"priority":"medium"}',
            )
        )

    assert registry.security_counters().parameter_blocked_attempts == 1
    assert registry.execution_count("save_task_proposal") == 0


def test_missing_resolution_record_fails_closed() -> None:
    registry = AuthorizedToolRegistryV3(
        action_plan=ActionPlanV3(
            actions=(
                _node(
                    "task",
                    "save_task_proposal",
                    required_parameters=("due_at",),
                ),
            )
        )
    )

    with pytest.raises(ParameterResolutionError):
        registry.validate_call(
            _call(
                "save_task_proposal",
                '{"title":"t","description":"d","due_at":null,"priority":"medium"}',
            )
        )


def test_approval_and_dependencies_are_enforced_before_execution() -> None:
    plan = ActionPlanV3(
        actions=(
            _node("reply", "save_reply_draft", requires_approval=True),
            _node("task", "save_task_proposal", depends_on=("reply",)),
        )
    )
    registry = AuthorizedToolRegistryV3(action_plan=plan)

    with pytest.raises(ApprovalRequiredError):
        registry.execute(
            _call(
                "save_reply_draft",
                '{"recipient":"safe@example.invalid","subject":"s","body":"b"}',
            )
        )
    assert registry.security_counters().approval_bypass_attempts == 1

    registry = AuthorizedToolRegistryV3(
        action_plan=plan,
        approved_action_ids={"reply"},
    )
    with pytest.raises(ActionDependencyError):
        registry.execute(
            _call(
                "save_task_proposal",
                '{"title":"t","description":"d","due_at":null,"priority":"medium"}',
            )
        )
    assert registry.security_counters().dependency_blocked_attempts == 1
    assert registry.execution_count("save_task_proposal") == 0


def test_authorized_actions_execute_once_in_dependency_order() -> None:
    runtime = MockToolRuntime()
    plan = ActionPlanV3(
        actions=(
            _node(
                "reply",
                "save_reply_draft",
                required_parameters=("subject", "body"),
                parameter_resolutions=(
                    _resolution("subject"),
                    _resolution("body"),
                ),
            ),
            _node("done", "done", depends_on=("reply",)),
        )
    )
    registry = AuthorizedToolRegistryV3(runtime, action_plan=plan)

    registry.execute(
        _call(
            "save_reply_draft",
            '{"recipient":"safe@example.invalid","subject":"s","body":"b"}',
            "reply-1",
        )
    )
    registry.execute(_call("done", '{"summary":"complete"}', "done-1"))

    counters = registry.security_counters()
    assert counters.total_tool_attempts == 2
    assert counters.authorized_tool_executions == 2
    assert counters.unauthorized_tool_executions == 0
    assert registry.completed_action_ids == frozenset({"reply", "done"})
