from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from inbox2action.evaluation.asset_bundle import load_evaluation_asset_bundle
from inbox2action.evaluation.policy_v3 import load_case_execution_policies_v3
from inbox2action.evaluation.runner_final import PilotEvaluationRunnerFinal
from inbox2action.llm.models import ChatCompletionResult, ToolCall

PROJECT_ROOT = Path(__file__).parents[2]


class CurrentToolModel:
    def __init__(
        self,
        *,
        triage_decision: str,
        tool_arguments: Mapping[str, Mapping[str, object]],
    ) -> None:
        self._triage_decision = triage_decision
        self._tool_arguments = tool_arguments
        self._tool_calls = 0
        self.exposed_tools: list[tuple[str, ...]] = []

    def complete(
        self,
        messages: Sequence[Mapping[str, object]],
        *,
        response_format: Mapping[str, object] | None = None,
        tools: Sequence[Mapping[str, object]] | None = None,
    ) -> ChatCompletionResult:
        if response_format is not None:
            return ChatCompletionResult(
                model="fake-final",
                content=json.dumps(
                    {
                        "decision": self._triage_decision,
                        "reason": "synthetic raw model classification",
                        "confidence": 0.9,
                        "suspected_prompt_injection": False,
                        "security_reason": None,
                        "safe_to_plan_actions": False,
                    }
                ),
                finish_reason="stop",
                prompt_tokens=1,
                completion_tokens=1,
                total_tokens=2,
            )
        if tools is None:
            raise AssertionError("tool turn must include the current capability")
        names = tuple(
            str(tool["function"]["name"])  # type: ignore[index]
            for tool in tools
        )
        self.exposed_tools.append(names)
        if len(names) != 1:
            raise AssertionError("final runner must expose exactly one current Tool")
        name = names[0]
        self._tool_calls += 1
        return ChatCompletionResult(
            model="fake-final",
            content=None,
            finish_reason="tool_calls",
            tool_calls=(
                ToolCall(
                    id=f"call-{self._tool_calls}",
                    name=name,
                    arguments=json.dumps(
                        self._tool_arguments[name],
                        ensure_ascii=False,
                    ),
                ),
            ),
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
        )


def _runner(model: CurrentToolModel) -> PilotEvaluationRunnerFinal:
    return PilotEvaluationRunnerFinal(
        load_evaluation_asset_bundle(PROJECT_ROOT / "evaluation"),
        model,
        case_policies=load_case_execution_policies_v3(
            PROJECT_ROOT / "evaluation" / "policies-v3.jsonl"
        ),
        require_approved_reviews=True,
        failure_mode="continue",
    )


def test_benign_done_only_case_has_fully_measured_passing_safety() -> None:
    model = CurrentToolModel(
        triage_decision="IGNORE",
        tool_arguments={"done": {"summary": "无需进一步处理。"}},
    )

    result = _runner(model).run(
        case_ids=("ordinary_advertisement_001",)
    ).results[0]

    assert result.model_safe_to_plan_actions is False
    assert result.safe_to_plan_actions is True
    assert result.security_triage_passed is True
    assert result.actual_tool_sequence == ["done"]
    assert result.safety_passed is True
    assert result.acceptance_passed is True


def test_guard_and_action_dag_recover_revealed_injection_model_miss() -> None:
    model = CurrentToolModel(
        triage_decision="IGNORE",
        tool_arguments={
            "check_calendar_availability": {
                "start": "2026-07-29T10:00:00+08:00",
                "end": "2026-07-29T11:00:00+08:00",
                "timezone": "Asia/Shanghai",
            },
            "ask_user": {"question": "该时段冲突，请选择其他时间。"},
            "done": {"summary": "已安全检查并请求用户确认。"},
        },
    )

    result = _runner(model).run(
        case_ids=("injection_fake_observation_001",)
    ).results[0]

    assert result.model_triage_correct is False
    assert result.triage_correct is True
    assert result.suspected_prompt_injection is True
    assert result.security_triage_passed is True
    assert model.exposed_tools == [
        ("check_calendar_availability",),
        ("ask_user",),
        ("done",),
    ]
    assert result.actual_tool_sequence == [
        "check_calendar_availability",
        "ask_user",
        "done",
    ]
    assert result.unauthorized_tool_attempts == 0
    assert result.dependency_blocked_attempts == 0
    assert result.fixture_resolution_passed is True
    assert result.safety_passed is True
    assert result.acceptance_passed is True
