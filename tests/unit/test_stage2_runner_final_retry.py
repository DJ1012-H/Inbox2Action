from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from inbox2action.evaluation.asset_bundle import load_evaluation_asset_bundle
from inbox2action.evaluation.policy_v3 import load_case_execution_policies_v3
from inbox2action.evaluation.runner_final import PilotEvaluationRunnerFinal
from inbox2action.llm.models import ChatCompletionResult, ToolCall

PROJECT_ROOT = Path(__file__).parents[2]


class InvalidThenCorrectCalendarModel:
    def __init__(self) -> None:
        self.tool_turn = 0

    def complete(
        self,
        messages: Sequence[Mapping[str, object]],
        *,
        response_format: Mapping[str, object] | None = None,
        tools: Sequence[Mapping[str, object]] | None = None,
    ) -> ChatCompletionResult:
        if response_format is not None:
            return ChatCompletionResult(
                model="fake",
                content=json.dumps(
                    {
                        "decision": "ACTION_REQUIRED",
                        "reason": "calendar request",
                        "confidence": 0.9,
                        "suspected_prompt_injection": False,
                        "security_reason": None,
                        "safe_to_plan_actions": True,
                    }
                ),
                finish_reason="stop",
                prompt_tokens=1,
                completion_tokens=1,
                total_tokens=2,
            )
        if tools is None or len(tools) != 1:
            raise AssertionError("one Tool must be exposed")
        name = str(tools[0]["function"]["name"])  # type: ignore[index]
        self.tool_turn += 1
        if name == "check_calendar_availability" and self.tool_turn == 1:
            arguments: dict[str, object] = {
                "start": "2026-08-03 13:00",
                "timezone": "Asia/Shanghai",
            }
        elif name == "check_calendar_availability":
            arguments = {
                "start": "2026-08-03T13:00:00+08:00",
                "end": "2026-08-03T14:00:00+08:00",
                "timezone": "Asia/Shanghai",
            }
        elif name == "ask_user":
            arguments = {"question": "该时段冲突，请提供其他时间。"}
        elif name == "done":
            arguments = {"summary": "已检查并请求用户确认。"}
        else:
            raise AssertionError(name)
        return ChatCompletionResult(
            model="fake",
            content=None,
            finish_reason="tool_calls",
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            tool_calls=(
                ToolCall(
                    id=f"call-{self.tool_turn}",
                    name=name,
                    arguments=json.dumps(arguments, ensure_ascii=False),
                ),
            ),
        )


def test_final_repairs_invalid_calendar_schema_before_authorization() -> None:
    bundle = load_evaluation_asset_bundle(PROJECT_ROOT / "evaluation")
    policies = load_case_execution_policies_v3(
        PROJECT_ROOT / "evaluation" / "policies-v3.jsonl"
    )
    model = InvalidThenCorrectCalendarModel()

    result = PilotEvaluationRunnerFinal(
        bundle,
        model,
        case_policies=policies,
        require_approved_reviews=True,
        failure_mode="continue",
    ).run(case_ids=("calendar_conflict_future_007",)).results[0]

    assert model.tool_turn == 4
    assert result.actual_tool_sequence == [
        "check_calendar_availability",
        "ask_user",
        "done",
    ]
    assert result.arguments_valid is True
    assert result.safety_passed is True
    assert result.acceptance_passed is True
