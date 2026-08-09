from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from pydantic import JsonValue

from inbox2action.evaluation.asset_bundle import load_evaluation_asset_bundle
from inbox2action.evaluation.assets import EvaluationCaseV1
from inbox2action.evaluation.policy_v3 import load_case_execution_policies_v3
from inbox2action.evaluation.runner_final import PilotEvaluationRunnerFinal
from inbox2action.llm.models import ChatCompletionResult, ToolCall

PROJECT_ROOT = Path(__file__).parents[2]


class GoldReplayModel:
    """Exercise all deterministic plumbing; this is not real-model evidence."""

    def __init__(self, case: EvaluationCaseV1) -> None:
        self._case = case
        self._call_index = 0

    def complete(
        self,
        messages: Sequence[Mapping[str, object]],
        *,
        response_format: Mapping[str, object] | None = None,
        tools: Sequence[Mapping[str, object]] | None = None,
    ) -> ChatCompletionResult:
        if response_format is not None:
            return ChatCompletionResult(
                model="gold-replay-not-an-evaluation",
                content=json.dumps(
                    {
                        "decision": self._case.expected.triage.value,
                        "reason": "deterministic integration fixture",
                        "confidence": 1.0,
                        "suspected_prompt_injection": False,
                        "security_reason": None,
                        "safe_to_plan_actions": True,
                    }
                ),
                finish_reason="stop",
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
            )
        if tools is None or len(tools) != 1:
            raise AssertionError("final runner must expose one current Tool")
        name = str(tools[0]["function"]["name"])  # type: ignore[index]
        self._call_index += 1
        return ChatCompletionResult(
            model="gold-replay-not-an-evaluation",
            content=None,
            finish_reason="tool_calls",
            tool_calls=(
                ToolCall(
                    id=f"gold-{self._call_index}",
                    name=name,
                    arguments=json.dumps(
                        self._arguments(name),
                        ensure_ascii=False,
                    ),
                ),
            ),
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
        )

    def _arguments(self, tool_name: str) -> dict[str, JsonValue]:
        asserted = self._case.expected.argument_assertions.get(tool_name, {})
        arguments = {
            key: _materialize(value)
            for key, value in asserted.items()
        }
        if tool_name == "ask_user":
            arguments.setdefault("question", "请补充缺失或冲突的信息。")
        elif tool_name == "done":
            arguments.setdefault("summary", "已完成授权的本地处理。")
        return arguments


def _materialize(value: JsonValue) -> JsonValue:
    if isinstance(value, dict) and set(value) == {"$contains_all"}:
        fragments = value["$contains_all"]
        if isinstance(fragments, list):
            return " ".join(str(fragment) for fragment in fragments)
        if isinstance(fragments, str):
            return fragments
        raise AssertionError("$contains_all must contain strings")
    return value


def test_final_diagnostic_replay_exposes_one_known_priority_inconsistency() -> None:
    """Validate plumbing while retaining the revealed inconsistent Gold Label."""

    bundle = load_evaluation_asset_bundle(PROJECT_ROOT / "evaluation")
    policies = load_case_execution_policies_v3(
        PROJECT_ROOT / "evaluation" / "policies-v3.jsonl"
    )
    results = []
    for case in bundle.cases:
        result = PilotEvaluationRunnerFinal(
            bundle,
            GoldReplayModel(case),
            case_policies=policies,
            require_approved_reviews=True,
            failure_mode="continue",
        ).run_case(case)
        results.append(result)

    assert len(results) == 60
    assert sum(result.acceptance_passed is True for result in results) == 59
    assert {
        result.case_id
        for result in results
        if result.acceptance_passed is not True
    } == {"multi_task_reply_003"}
    assert all(result.safety_passed is True for result in results)
    assert all(result.unauthorized_tool_attempts == 0 for result in results)
    assert all(result.dependency_blocked_attempts == 0 for result in results)
