from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from inbox2action.evaluation.asset_bundle import load_evaluation_asset_bundle
from inbox2action.llm.candidate_final import CandidateChatClientFinal
from inbox2action.llm.models import ChatCompletionResult, ToolCall

PROJECT_ROOT = Path(__file__).parents[2]


class RecordingDelegate:
    def __init__(self, *responses: ChatCompletionResult) -> None:
        self.responses = list(responses)
        self.messages: list[list[dict[str, object]]] = []

    def complete(
        self,
        messages: Sequence[Mapping[str, object]],
        *,
        response_format: Mapping[str, object] | None = None,
        tools: Sequence[Mapping[str, object]] | None = None,
    ) -> ChatCompletionResult:
        self.messages.append([dict(message) for message in messages])
        return self.responses.pop(0)


def _result(
    name: str,
    arguments: dict[str, object],
    *,
    call_id: str,
    tokens: int,
) -> ChatCompletionResult:
    return ChatCompletionResult(
        model="fake",
        content=None,
        finish_reason="tool_calls",
        prompt_tokens=tokens,
        completion_tokens=tokens,
        total_tokens=tokens * 2,
        tool_calls=(
            ToolCall(
                id=call_id,
                name=name,
                arguments=json.dumps(arguments),
            ),
        ),
    )


def _calendar_tool() -> list[dict[str, object]]:
    from inbox2action.tools.registry import ToolRegistry

    return ToolRegistry(
        enabled_tool_names={"check_calendar_availability"}
    ).openai_tools()


def test_schema_invalid_call_is_retried_once_before_tool_boundary() -> None:
    raw_marker = "PRIVATE-invalid-argument"
    first = _result(
        "check_calendar_availability",
        {"start": raw_marker},
        call_id="first",
        tokens=2,
    )
    second = _result(
        "check_calendar_availability",
        {
            "start": "2026-08-03T13:00:00+08:00",
            "end": "2026-08-03T14:00:00+08:00",
            "timezone": "Asia/Shanghai",
        },
        call_id="second",
        tokens=3,
    )
    delegate = RecordingDelegate(first, second)

    case = next(
        case
        for case in load_evaluation_asset_bundle(
            PROJECT_ROOT / "evaluation"
        ).cases
        if case.case_id == "calendar_conflict_future_007"
    )
    result = CandidateChatClientFinal(
        delegate,
        case=case,
        policy_has_actions=True,
    ).complete(
        [{"role": "system", "content": "base"}],
        tools=_calendar_tool(),
    )

    assert result.tool_calls[0].id == "second"
    assert result.prompt_tokens == 5
    assert result.completion_tokens == 5
    assert result.total_tokens == 10
    assert len(delegate.messages) == 2
    assert raw_marker not in json.dumps(delegate.messages[1])


def test_unexposed_tool_is_not_hidden_by_schema_retry() -> None:
    response = _result(
        "execute_shell",
        {},
        call_id="unknown",
        tokens=1,
    )
    delegate = RecordingDelegate(response)

    case = next(
        case
        for case in load_evaluation_asset_bundle(
            PROJECT_ROOT / "evaluation"
        ).cases
        if case.case_id == "calendar_conflict_future_007"
    )
    result = CandidateChatClientFinal(
        delegate,
        case=case,
        policy_has_actions=True,
    ).complete(
        [{"role": "system", "content": "base"}],
        tools=_calendar_tool(),
    )

    assert result.tool_calls[0].name == "execute_shell"
    assert len(delegate.messages) == 1
