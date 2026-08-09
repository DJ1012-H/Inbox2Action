from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from inbox2action.evaluation.asset_bundle import load_evaluation_asset_bundle
from inbox2action.evaluation.policy_v3 import load_case_execution_policies_v3
from inbox2action.evaluation.runner_final import PilotEvaluationRunnerFinal
from inbox2action.llm.models import ChatCompletionResult, ToolCall

PROJECT_ROOT = Path(__file__).parents[2]


class WrongDateModel:
    def __init__(self) -> None:
        self.turn = 0

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
        self.turn += 1
        arguments: dict[str, object]
        if name == "check_calendar_availability":
            arguments = {
                "start": "2026-08-05T14:00:00+08:00",
                "end": "2026-08-05T15:00:00+08:00",
                "timezone": "Asia/Shanghai",
            }
        elif name == "done":
            arguments = {"summary": "已检查时间。"}
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
                    id=f"call-{self.turn}",
                    name=name,
                    arguments=json.dumps(arguments, ensure_ascii=False),
                ),
            ),
        )


def test_final_normalized_interval_matches_fixture_and_gold() -> None:
    bundle = load_evaluation_asset_bundle(PROJECT_ROOT / "evaluation")
    policies = load_case_execution_policies_v3(
        PROJECT_ROOT / "evaluation" / "policies-v3.jsonl"
    )

    result = PilotEvaluationRunnerFinal(
        bundle,
        WrongDateModel(),
        case_policies=policies,
        require_approved_reviews=True,
        failure_mode="continue",
    ).run(case_ids=("calendar_relative_weekday_005",)).results[0]

    assert result.fixture_resolution_passed is True
    assert result.arguments_valid is True
    assert result.safety_passed is True
    assert result.acceptance_passed is True
