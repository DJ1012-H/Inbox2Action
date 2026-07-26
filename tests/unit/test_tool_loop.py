from __future__ import annotations

import json
from typing import Any

import pytest

from inbox2action.agent.tool_loop import (
    CompletionWithoutDoneError,
    DuplicateToolCallError,
    EmptyModelResponseError,
    ReplanningRequiredError,
    RequiredToolNotCalledError,
    ToolLoop,
    ToolLoopError,
    ToolLoopLimitError,
    ToolLoopProtocolError,
    UnsafeCompletionClaimError,
)
from inbox2action.llm.models import ChatCompletionResult, ToolCall
from inbox2action.tools.mock_tools import MockToolRuntime
from inbox2action.tools.policy import (
    InvalidToolArgumentsError,
    ObservationValidationError,
    ToolExecutionError,
    ToolIdMismatchError,
    UnknownToolError,
)
from inbox2action.tools.registry import ToolRegistry


class ScriptedModel:
    def __init__(self, *responses: ChatCompletionResult) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def complete(
        self, messages: Any, *, tools: Any = None, response_format: Any = None
    ) -> ChatCompletionResult:
        self.calls.append(
            {"messages": messages, "tools": tools, "response_format": response_format}
        )
        if not self.responses:
            raise AssertionError("scripted model exhausted")
        return self.responses.pop(0)


def tool_response(
    name: str, arguments: dict[str, object], call_id: str
) -> ChatCompletionResult:
    return ChatCompletionResult(
        model="deepseek-v4-flash",
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


def text_response(content: str) -> ChatCompletionResult:
    return ChatCompletionResult(
        model="deepseek-v4-flash",
        content=content,
        finish_reason="stop",
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
    )


def run(model: ScriptedModel, registry: ToolRegistry | None = None, **kwargs: object):
    return ToolLoop(model, registry or ToolRegistry(), **kwargs).run(
        [{"role": "user", "content": "人工构造的会议邮件"}]
    )


def done_response(call_id: str = "done-1") -> ChatCompletionResult:
    return tool_response("done", {"summary": "已完成安全流程"}, call_id)


def calendar_response(call_id: str, start: str, end: str) -> ChatCompletionResult:
    return tool_response(
        "check_calendar_availability",
        {"start": start, "end": end},
        call_id,
    )


def test_valid_loop_passes_tools_and_finishes_with_done() -> None:
    model = ScriptedModel(
        tool_response("get_current_time", {}, "time-1"),
        done_response(),
    )

    result = run(model)

    assert result.completed is True
    assert [entry.tool_name for entry in result.trace] == [
        "get_current_time",
        "done",
    ]
    assert len(model.calls) == 2
    assert {
        tool["function"]["name"]
        for tool in model.calls[0]["tools"]
        if isinstance(tool["function"], dict)
    } == {
        "get_current_time",
        "check_calendar_availability",
        "save_reply_draft",
        "ask_user",
        "done",
    }


def test_max_tool_steps_is_hard_and_finite() -> None:
    model = ScriptedModel(
        tool_response("get_current_time", {}, "time-1"),
        tool_response("ask_user", {"question": "请确认时间"}, "ask-1"),
        done_response(),
    )

    with pytest.raises(ToolLoopLimitError) as captured:
        run(model, max_tool_steps=2)

    assert len(captured.value.trace) == 2
    assert len(model.calls) == 2


def test_same_tool_and_validated_arguments_are_not_repeated() -> None:
    model = ScriptedModel(
        tool_response("get_current_time", {}, "time-1"),
        tool_response("get_current_time", {}, "time-2"),
    )

    with pytest.raises(DuplicateToolCallError):
        run(model)


@pytest.mark.parametrize(
    "response,expected",
    [
        (tool_response("send_email", {}, "bad-1"), UnknownToolError),
        (
            ChatCompletionResult(
                model="deepseek-v4-flash",
                content=None,
                finish_reason="tool_calls",
                prompt_tokens=1,
                completion_tokens=1,
                total_tokens=2,
                tool_calls=(ToolCall("bad-1", "get_current_time", "not-json"),),
            ),
            InvalidToolArgumentsError,
        ),
    ],
)
def test_unknown_or_invalid_tool_calls_are_blocked_before_execution(
    response: ChatCompletionResult,
    expected: type[Exception],
) -> None:
    registry = ToolRegistry()
    model = ScriptedModel(response)

    with pytest.raises(expected):
        run(model, registry)

    assert registry.execution_count("send_email") == 0
    assert registry.execution_count("get_current_time") == 0


def test_model_text_without_done_is_not_accepted_as_completion() -> None:
    model = ScriptedModel(text_response("我已经创建了日程。"))

    with pytest.raises(CompletionWithoutDoneError):
        run(model)


def test_empty_model_response_is_rejected() -> None:
    model = ScriptedModel(
        ChatCompletionResult(
            model="deepseek-v4-flash",
            content=None,
            finish_reason=None,
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
        )
    )

    with pytest.raises(EmptyModelResponseError):
        run(model)


def test_repeated_tool_id_is_rejected() -> None:
    model = ScriptedModel(
        tool_response("get_current_time", {}, "same-id"),
        tool_response("ask_user", {"question": "确认时间"}, "same-id"),
    )

    with pytest.raises(ToolLoopProtocolError):
        run(model)


def test_multiple_tool_calls_in_one_turn_are_rejected() -> None:
    response = ChatCompletionResult(
        model="deepseek-v4-flash",
        content=None,
        finish_reason="tool_calls",
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
        tool_calls=(
            ToolCall("one", "get_current_time", "{}"),
            ToolCall("two", "done", '{"summary":"完成"}'),
        ),
    )

    with pytest.raises(ToolLoopProtocolError):
        run(ScriptedModel(response))


def test_tool_exception_and_invalid_observation_are_not_silent() -> None:
    failing_registry = ToolRegistry(
        handler_overrides={
            "get_current_time": lambda _: (_ for _ in ()).throw(RuntimeError("fake")),
        }
    )
    with pytest.raises(ToolExecutionError):
        run(
            ScriptedModel(tool_response("get_current_time", {}, "time-1")),
            failing_registry,
        )

    invalid_registry = ToolRegistry(
        handler_overrides={"get_current_time": lambda _: {"tool_name": "wrong"}}
    )
    with pytest.raises(ObservationValidationError):
        run(
            ScriptedModel(tool_response("get_current_time", {}, "time-1")),
            invalid_registry,
        )


def test_save_reply_draft_is_only_an_in_memory_proposal_and_trace_is_redacted() -> None:
    runtime = MockToolRuntime()
    registry = ToolRegistry(runtime)
    model = ScriptedModel(
        tool_response(
            "save_reply_draft",
            {
                "recipient": "fake@example.invalid",
                "subject": "主题",
                "body": "这是一段仅用于测试的草稿正文",
            },
            "draft-1",
        ),
        done_response(),
    )

    result = run(model, registry)

    assert len(runtime.proposals) == 1
    assert result.proposals[0].subject == "主题"
    assert result.trace[0].validated_arguments["body_length"] > 0
    assert "这是一段仅用于测试的草稿正文" not in str(result.trace)


def test_calendar_conflict_requires_replanning_before_done() -> None:
    conflict = calendar_response(
        "calendar-1",
        "2026-07-27T09:00:00+08:00",
        "2026-07-27T10:00:00+08:00",
    )
    model = ScriptedModel(conflict, done_response("done-1"))

    with pytest.raises(ReplanningRequiredError):
        run(model)


def test_calendar_conflict_changes_trace_after_asking_user() -> None:
    model = ScriptedModel(
        calendar_response(
            "calendar-1",
            "2026-07-27T09:00:00+08:00",
            "2026-07-27T10:00:00+08:00",
        ),
        tool_response("ask_user", {"question": "原时间有冲突，请提供新时间"}, "ask-1"),
        done_response("done-1"),
    )

    result = run(model)

    assert [entry.status for entry in result.trace] == [
        "conflict",
        "waiting_for_user",
        "complete",
    ]


def test_same_conflicting_interval_does_not_loop_forever() -> None:
    conflict = calendar_response(
        "calendar-1",
        "2026-07-27T09:00:00+08:00",
        "2026-07-27T10:00:00+08:00",
    )
    model = ScriptedModel(
        conflict,
        calendar_response(
            "calendar-2", "2026-07-27T09:00:00+08:00", "2026-07-27T10:00:00+08:00"
        ),
    )

    with pytest.raises(DuplicateToolCallError):
        run(model)


def test_new_calendar_candidate_allows_done() -> None:
    model = ScriptedModel(
        calendar_response(
            "calendar-1",
            "2026-07-27T09:00:00+08:00",
            "2026-07-27T10:00:00+08:00",
        ),
        calendar_response(
            "calendar-2",
            "2026-07-27T11:00:00+08:00",
            "2026-07-27T12:00:00+08:00",
        ),
        done_response("done-1"),
    )

    result = run(model)

    assert result.completed is True
    assert [entry.tool_name for entry in result.trace] == [
        "check_calendar_availability",
        "check_calendar_availability",
        "done",
    ]


def test_required_calendar_check_blocks_done_without_availability_observation() -> None:
    with pytest.raises(RequiredToolNotCalledError):
        run(
            ScriptedModel(done_response()),
            required_tools_before_done=("check_calendar_availability",),
        )


def test_unsupported_calendar_event_claim_is_blocked() -> None:
    model = ScriptedModel(
        calendar_response(
            "calendar-1",
            "2026-07-27T11:00:00+08:00",
            "2026-07-27T12:00:00+08:00",
        ),
        tool_response("done", {"summary": "已创建 Calendar Event"}, "done-1"),
    )

    with pytest.raises(UnsafeCompletionClaimError):
        run(
            model,
            required_tools_before_done=("check_calendar_availability",),
        )


def test_tool_id_mismatch_and_loop_limit_constructor_are_rejected() -> None:
    invalid_registry = ToolRegistry(
        handler_overrides={
            "get_current_time": lambda _: {
                "tool_name": "get_current_time",
                "observation_type": "current_time",
                "status": "ok",
                "tool_call_id": "other-id",
            }
        }
    )
    with pytest.raises(ToolIdMismatchError):
        run(
            ScriptedModel(tool_response("get_current_time", {}, "time-1")),
            invalid_registry,
        )

    with pytest.raises(ValueError):
        ToolLoop(ScriptedModel(), ToolRegistry(), max_tool_steps=0)
    with pytest.raises(ValueError):
        ToolLoop(ScriptedModel(), ToolRegistry(), max_tool_steps=21)


def test_tool_errors_carry_only_redacted_trace_metadata() -> None:
    model = ScriptedModel(
        tool_response(
            "save_reply_draft",
            {"subject": "主题", "body": "脱敏正文"},
            "draft-1",
        ),
        tool_response(
            "save_reply_draft", {"subject": "主题", "body": "脱敏正文"}, "draft-2"
        ),
    )

    with pytest.raises(ToolLoopError) as captured:
        run(model)

    assert captured.value.trace[0].tool_name == "save_reply_draft"
    assert "脱敏正文" not in str(captured.value.trace)
