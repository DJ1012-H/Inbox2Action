from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from inbox2action.evaluation.asset_bundle import load_evaluation_asset_bundle
from inbox2action.evaluation.policy_v3 import load_case_execution_policies_v3
from inbox2action.evaluation.runner_final import PilotEvaluationRunnerFinal
from inbox2action.llm.models import ChatCompletionResult, ToolCall

PROJECT_ROOT = Path(__file__).parents[2]


class HighPriorityRelativeTaskModel:
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
                        "reason": "task request",
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
        if name == "save_task_proposal":
            arguments: dict[str, object] = {
                "title": "更新 Atlas 供应商清单",
                "description": "更新 Atlas 供应商清单",
                "due_at": "2026-07-28T12:00:00+08:00",
                "priority": "high",
            }
        elif name == "done":
            arguments = {"summary": "已保存任务建议。"}
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


def test_final_runner_accepts_normalized_relative_task() -> None:
    bundle = load_evaluation_asset_bundle(PROJECT_ROOT / "evaluation")
    policies = load_case_execution_policies_v3(
        PROJECT_ROOT / "evaluation" / "policies-v3.jsonl"
    )

    result = PilotEvaluationRunnerFinal(
        bundle,
        HighPriorityRelativeTaskModel(),
        case_policies=policies,
        require_approved_reviews=True,
        failure_mode="continue",
    ).run(case_ids=("task_relative_tomorrow_003",)).results[0]

    assert result.arguments_valid is True
    assert result.safety_passed is True
    assert result.acceptance_passed is True
