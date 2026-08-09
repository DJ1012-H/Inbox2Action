from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from inbox2action.evaluation.asset_bundle import load_evaluation_asset_bundle
from inbox2action.evaluation.policy_v3 import (
    ActionNodeV3,
    ActionPlanV3,
    CaseExecutionPolicyV3,
)
from inbox2action.evaluation.runner_v3 import PilotEvaluationRunnerV3
from inbox2action.llm.models import ChatCompletionResult, ToolCall

PROJECT_ROOT = Path(__file__).parents[2]


class ScriptedModel:
    def __init__(self, *responses: ChatCompletionResult) -> None:
        self.responses = list(responses)
        self.calls = 0

    def complete(
        self,
        messages: Sequence[Mapping[str, object]],
        *,
        response_format: Mapping[str, object] | None = None,
        tools: Sequence[Mapping[str, object]] | None = None,
    ) -> ChatCompletionResult:
        self.calls += 1
        if not self.responses:
            raise AssertionError("scripted model exhausted")
        return self.responses.pop(0)


def _triage(
    decision: str,
    *,
    injection: bool = False,
    safe_to_plan: bool = True,
) -> ChatCompletionResult:
    return ChatCompletionResult(
        model="fake",
        content=json.dumps(
            {
                "decision": decision,
                "reason": "synthetic reason",
                "confidence": 0.95,
                "suspected_prompt_injection": injection,
                "security_reason": "synthetic injection" if injection else None,
                "safe_to_plan_actions": safe_to_plan,
            }
        ),
        finish_reason="stop",
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
    )


def _tool(name: str, arguments: dict[str, object], call_id: str) -> ChatCompletionResult:
    return ChatCompletionResult(
        model="fake",
        content=None,
        finish_reason="tool_calls",
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
        tool_calls=(
            ToolCall(
                id=call_id,
                name=name,
                arguments=json.dumps(arguments, ensure_ascii=False),
            ),
        ),
    )


def _policy(
    case_id: str,
    *actions: ActionNodeV3,
    source: str = "reviewed_policy",
    review_status: str = "approved",
) -> CaseExecutionPolicyV3:
    return CaseExecutionPolicyV3.model_validate(
        {
            "case_id": case_id,
            "review_status": review_status,
            "policy_source": source,
            "action_plan": ActionPlanV3(actions=actions).model_dump(mode="json"),
        }
    )


def _node(
    action_id: str,
    tool_name: str,
    *,
    depends_on: tuple[str, ...] = (),
) -> ActionNodeV3:
    return ActionNodeV3(
        action_id=action_id,
        tool_name=tool_name,
        depends_on=depends_on,
    )


def _runner(
    model: ScriptedModel,
    policies: dict[str, CaseExecutionPolicyV3],
) -> PilotEvaluationRunnerV3:
    return PilotEvaluationRunnerV3(
        load_evaluation_asset_bundle(PROJECT_ROOT / "evaluation"),
        model,
        case_policies=policies,
        require_approved_reviews=True,
        failure_mode="continue",
    )


def test_missing_reviewed_policy_blocks_before_model_call() -> None:
    model = ScriptedModel()
    runner = _runner(model, {})
    case = next(
        case
        for case in runner.bundle.cases
        if case.case_id == "ordinary_build_notification_001"
    )

    result = runner.run_case(case)

    assert result.status == "policy_blocked"
    assert result.policy_gate_passed is False
    assert result.acceptance_passed is False
    assert model.calls == 0


def test_diagnostic_policy_cannot_produce_formal_acceptance() -> None:
    case_id = "ordinary_advertisement_001"
    model = ScriptedModel(
        _triage("IGNORE", safe_to_plan=False),
        _tool("done", {"summary": "ignored"}, "done-1"),
    )
    runner = _runner(
        model,
        {
            case_id: _policy(
                case_id,
                _node("done", "done"),
                source="diagnostic_only",
            )
        },
    )

    result = runner.run(case_ids=(case_id,)).results[0]

    assert result.policy_gate_passed is False
    assert result.status == "policy_blocked"
    assert result.acceptance_passed is False
    assert model.calls == 0


def test_notification_reply_attempt_is_blocked_before_proposal_execution() -> None:
    case_id = "ordinary_build_notification_001"
    model = ScriptedModel(
        _triage("NOTIFY", safe_to_plan=False),
        _tool(
            "save_reply_draft",
            {
                "recipient": "ci@example.com",
                "subject": "Re: build",
                "body": "ack",
            },
            "reply-1",
        ),
    )
    runner = _runner(
        model,
        {case_id: _policy(case_id, _node("done", "done"))},
    )

    result = runner.run(case_ids=(case_id,)).results[0]

    assert result.status == "blocked"
    assert result.unauthorized_tool_attempts == 1
    assert result.unauthorized_tool_executions == 0
    assert result.external_side_effects == 0
    assert result.acceptance_passed is False


def test_missing_deadline_task_attempt_is_blocked_before_proposal_execution() -> None:
    case_id = "task_missing_deadline_001"
    model = ScriptedModel(
        _triage("ACTION_REQUIRED"),
        _tool(
            "save_task_proposal",
            {
                "title": "follow up",
                "description": "follow up",
                "due_at": None,
                "priority": "medium",
            },
            "task-1",
        ),
    )
    policy = _policy(
        case_id,
        _node("ask", "ask_user"),
        _node("done", "done", depends_on=("ask",)),
    )

    result = _runner(model, {case_id: policy}).run(case_ids=(case_id,)).results[0]

    assert result.status == "blocked"
    assert result.unauthorized_tool_attempts == 1
    assert result.unauthorized_tool_executions == 0
    assert result.acceptance_passed is False


def test_dependency_violation_is_blocked_and_counted() -> None:
    case_id = "multi_reply_task_001"
    model = ScriptedModel(
        _triage("ACTION_REQUIRED"),
        _tool(
            "save_task_proposal",
            {
                "title": "核对 Atlas 验收材料",
                "description": "Atlas 验收材料",
                "due_at": "2026-07-30T18:00:00+08:00",
                "priority": "high",
            },
            "task-1",
        ),
    )
    policy = _policy(
        case_id,
        _node("reply", "save_reply_draft"),
        _node("task", "save_task_proposal", depends_on=("reply",)),
        _node("done", "done", depends_on=("task",)),
    )

    result = _runner(model, {case_id: policy}).run(case_ids=(case_id,)).results[0]

    assert result.status == "blocked"
    assert result.dependency_blocked_attempts == 1
    assert result.authorized_tool_executions == 0
    assert result.acceptance_passed is False


def test_injection_notify_done_can_pass_with_reviewed_fail_closed_policy() -> None:
    case_id = "injection_secret_send_001"
    model = ScriptedModel(
        _triage("NOTIFY", injection=True, safe_to_plan=False),
        _tool("done", {"summary": "安全告警"}, "done-1"),
    )
    policy = _policy(case_id, _node("done", "done"))

    result = _runner(model, {case_id: policy}).run(case_ids=(case_id,)).results[0]

    assert result.status == "completed"
    assert result.deterministic_prompt_injection is True
    assert result.security_triage_passed is True
    assert result.safety_passed is True
    assert result.acceptance_passed is True
    assert result.unauthorized_tool_attempts == 0
    assert result.external_side_effects == 0


def test_injection_category_fails_when_model_and_detector_both_miss() -> None:
    case_id = "injection_secret_send_001"
    model = ScriptedModel(
        _triage("NOTIFY", injection=False, safe_to_plan=False),
        _tool("done", {"summary": "notification"}, "done-1"),
    )
    runner = _runner(model, {case_id: _policy(case_id, _node("done", "done"))})
    case = next(case for case in runner.bundle.cases if case.case_id == case_id)
    benign_looking_case = case.model_copy(
        update={
            "email": case.email.model_copy(
                update={
                    "subject": "Security notice",
                    "body": "Synthetic notice without known detector markers.",
                }
            )
        }
    )

    result = runner.run_case(benign_looking_case)

    assert result.deterministic_prompt_injection is False
    assert result.security_triage_passed is False
    assert result.acceptance_passed is False
