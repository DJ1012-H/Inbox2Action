from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from inbox2action.evaluation.asset_bundle import load_evaluation_asset_bundle
from inbox2action.llm.candidate_final import CandidateChatClientFinal
from inbox2action.llm.models import ChatCompletionResult, ToolCall
from inbox2action.tools.registry import ToolRegistry

PROJECT_ROOT = Path(__file__).parents[2]


class OneResponseModel:
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


def _tool_response(name: str, arguments: dict[str, object]) -> ChatCompletionResult:
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
                name=name,
                arguments=json.dumps(arguments),
            ),
        ),
    )


def test_final_normalizes_calendar_interval_without_gold_or_fixture_access() -> None:
    bundle = load_evaluation_asset_bundle(PROJECT_ROOT / "evaluation")
    case = next(
        case
        for case in bundle.cases
        if case.case_id == "calendar_relative_weekday_005"
    )
    model = OneResponseModel(
        _tool_response(
            "check_calendar_availability",
            {
                "start": "2026-08-05T14:00:00+08:00",
                "end": "2026-08-05T15:00:00+08:00",
                "timezone": "Asia/Shanghai",
            },
        )
    )
    tools = ToolRegistry(
        enabled_tool_names={"check_calendar_availability"}
    ).openai_tools()

    response = CandidateChatClientFinal(
        model,
        case=case,
        policy_has_actions=True,
    ).complete([], tools=tools)
    arguments = json.loads(response.tool_calls[0].arguments)

    assert arguments == {
        "start": "2026-07-29T14:00:00+08:00",
        "end": "2026-07-29T15:00:00+08:00",
        "timezone": "Asia/Shanghai",
    }
