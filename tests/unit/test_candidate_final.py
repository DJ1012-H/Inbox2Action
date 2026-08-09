from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from inbox2action.evaluation.asset_bundle import load_evaluation_asset_bundle
from inbox2action.llm.candidate_final import CandidateChatClientFinal
from inbox2action.llm.models import ChatCompletionResult, ToolCall
from inbox2action.tools.registry import ToolRegistry

PROJECT_ROOT = Path(__file__).parents[2]


class StaticModel:
    def __init__(self, response: ChatCompletionResult) -> None:
        self.response = response

    def complete(
        self,
        messages: Sequence[Mapping[str, object]],
        *,
        response_format: Mapping[str, object] | None = None,
        tools: Sequence[Mapping[str, object]] | None = None,
    ) -> ChatCompletionResult:
        return self.response


def _task_response(priority: str) -> ChatCompletionResult:
    return ChatCompletionResult(
        model="fake",
        content=None,
        finish_reason="tool_calls",
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
        tool_calls=(
            ToolCall(
                id="call-1",
                name="save_task_proposal",
                arguments=json.dumps(
                    {
                        "title": "更新 Atlas 供应商清单",
                        "description": "更新 Atlas 供应商清单",
                        "due_at": "2026-07-28T12:00:00+08:00",
                        "priority": priority,
                    }
                ),
            ),
        ),
    )


def test_final_candidate_normalizes_nonurgent_relative_task_priority() -> None:
    bundle = load_evaluation_asset_bundle(PROJECT_ROOT / "evaluation")
    case = next(
        case
        for case in bundle.cases
        if case.case_id == "task_relative_tomorrow_003"
    )
    tools = ToolRegistry(
        enabled_tool_names={"save_task_proposal"}
    ).openai_tools()

    response = CandidateChatClientFinal(
        StaticModel(_task_response("high")),
        case=case,
        policy_has_actions=True,
    ).complete([], tools=tools)
    arguments = json.loads(response.tool_calls[0].arguments)

    assert arguments["due_at"] == "2026-07-27T12:00:00+08:00"
    assert arguments["priority"] == "medium"


def test_final_candidate_normalizes_explicit_deadline_priority() -> None:
    bundle = load_evaluation_asset_bundle(PROJECT_ROOT / "evaluation")
    case = next(
        case
        for case in bundle.cases
        if case.case_id == "multi_reply_task_001"
    )
    tools = ToolRegistry(
        enabled_tool_names={"save_task_proposal"}
    ).openai_tools()

    response = CandidateChatClientFinal(
        StaticModel(_task_response("medium")),
        case=case,
        policy_has_actions=True,
    ).complete([], tools=tools)
    arguments = json.loads(response.tool_calls[0].arguments)

    assert arguments["due_at"] == "2026-07-30T18:00:00+08:00"
    assert arguments["priority"] == "high"
