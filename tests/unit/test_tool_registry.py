from __future__ import annotations

import pytest

from inbox2action.llm.models import ToolCall
from inbox2action.tools.mock_tools import MockToolRuntime
from inbox2action.tools.policy import (
    InvalidToolArgumentsError,
    ObservationValidationError,
    ToolExecutionError,
    ToolIdMismatchError,
    UnknownToolError,
)
from inbox2action.tools.registry import ToolRegistry


def call(name: str, arguments: str, call_id: str = "call-1") -> ToolCall:
    return ToolCall(id=call_id, name=name, arguments=arguments)


def test_registry_exposes_only_the_explicit_safe_tools() -> None:
    names = {
        tool["function"]["name"]
        for tool in ToolRegistry().openai_tools()
        if isinstance(tool["function"], dict)
    }

    assert names == {
        "get_current_time",
        "check_calendar_availability",
        "save_reply_draft",
        "save_task_proposal",
        "ask_user",
        "done",
    }


def test_registry_can_hide_tools_without_runtime_support() -> None:
    registry = ToolRegistry(enabled_tool_names={"save_task_proposal", "done"})

    assert registry.openai_tool_names() == ("save_task_proposal", "done")
    with pytest.raises(UnknownToolError):
        registry.validate_call(call("get_current_time", "{}"))


def test_validated_call_is_required_before_execution() -> None:
    registry = ToolRegistry()

    observation = registry.execute(call("get_current_time", "{}"))

    assert observation.status == "ok"
    assert registry.execution_count("get_current_time") == 1


@pytest.mark.parametrize(
    "tool_call",
    [
        call("send_email", "{}"),
        call("get_current_time", "not-json"),
        call("get_current_time", "[]"),
        call("get_current_time", '{"extra":true}'),
        call(
            "check_calendar_availability",
            '{"start":"2026-07-27T09:00:00","end":"2026-07-27T10:00:00+08:00"}',
        ),
    ],
)
def test_invalid_or_unknown_tools_never_execute(tool_call: ToolCall) -> None:
    registry = ToolRegistry()

    with pytest.raises((UnknownToolError, InvalidToolArgumentsError)):
        registry.execute(tool_call)

    assert registry.execution_count(tool_call.name) == 0


def test_save_reply_draft_only_creates_an_in_memory_proposal() -> None:
    runtime = MockToolRuntime()
    registry = ToolRegistry(runtime)

    observation = registry.execute(
        call(
            "save_reply_draft",
            '{"recipient":"fake@example.invalid","subject":"主题","body":"正文"}',
        )
    )

    assert observation.status == "proposal_created"
    assert observation.data["external_side_effects"] == 0
    assert len(runtime.proposals) == 1
    assert runtime.proposals[0].body == "正文"


def test_invalid_observation_and_handler_exception_are_classified() -> None:
    invalid_registry = ToolRegistry(
        handler_overrides={
            "get_current_time": lambda _: {"tool_name": "wrong"},
        }
    )
    with pytest.raises(ObservationValidationError):
        invalid_registry.execute(call("get_current_time", "{}"))

    failing_registry = ToolRegistry(
        handler_overrides={
            "get_current_time": lambda _: (_ for _ in ()).throw(RuntimeError("fake")),
        }
    )
    with pytest.raises(ToolExecutionError):
        failing_registry.execute(call("get_current_time", "{}"))


def test_tool_observation_id_mismatch_is_rejected() -> None:
    registry = ToolRegistry(
        handler_overrides={
            "get_current_time": lambda _: {
                "tool_name": "get_current_time",
                "observation_type": "current_time",
                "status": "ok",
                "tool_call_id": "other-call",
            }
        }
    )

    with pytest.raises(ToolIdMismatchError):
        registry.execute(call("get_current_time", "{}"))
