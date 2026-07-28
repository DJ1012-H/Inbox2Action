from __future__ import annotations

import json
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from typing import Any, cast

from pydantic import BaseModel, ValidationError

from inbox2action.llm.models import ToolCall
from inbox2action.tools.mock_tools import MockToolRuntime, ToolObservation
from inbox2action.tools.policy import (
    InvalidToolArgumentsError,
    ObservationValidationError,
    ToolError,
    ToolExecutionError,
    ToolIdMismatchError,
    UnknownToolError,
    canonical_arguments,
    require_allowed_tool,
    trace_arguments,
)
from inbox2action.tools.schemas import (
    AskUserArgs,
    CheckCalendarAvailabilityArgs,
    DoneArgs,
    NoArguments,
    SaveReplyDraftArgs,
    SaveTaskProposalArgs,
)

ToolHandler = Callable[[BaseModel], object]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    argument_model: type[BaseModel]
    handler: ToolHandler


@dataclass(frozen=True)
class ValidatedToolCall:
    call: ToolCall
    arguments: BaseModel
    signature: str
    trace_arguments: Mapping[str, object]


class ToolRegistry:
    """The only execution boundary for checkpoint-two tools."""

    def __init__(
        self,
        runtime: MockToolRuntime | None = None,
        *,
        handler_overrides: Mapping[str, ToolHandler] | None = None,
        enabled_tool_names: Collection[str] | None = None,
    ) -> None:
        self.runtime = runtime or MockToolRuntime()
        handlers: dict[str, ToolHandler] = {
            "get_current_time": cast(ToolHandler, self.runtime.get_current_time),
            "check_calendar_availability": cast(
                ToolHandler,
                self.runtime.check_calendar_availability,
            ),
            "save_reply_draft": cast(ToolHandler, self.runtime.save_reply_draft),
            "save_task_proposal": cast(ToolHandler, self.runtime.save_task_proposal),
            "ask_user": cast(ToolHandler, self.runtime.ask_user),
            "done": cast(ToolHandler, self.runtime.done),
        }
        if handler_overrides is not None:
            for name, handler in handler_overrides.items():
                require_allowed_tool(name)
                handlers[name] = handler

        self._specs = {
            "get_current_time": ToolSpec(
                name="get_current_time",
                description="Read the deterministic current-time Mock Tool.",
                argument_model=NoArguments,
                handler=handlers["get_current_time"],
            ),
            "check_calendar_availability": ToolSpec(
                name="check_calendar_availability",
                description="Read deterministic calendar availability for an explicit interval.",
                argument_model=CheckCalendarAvailabilityArgs,
                handler=handlers["check_calendar_availability"],
            ),
            "save_reply_draft": ToolSpec(
                name="save_reply_draft",
                description="Create an in-memory reply proposal only; never sends or saves externally.",
                argument_model=SaveReplyDraftArgs,
                handler=handlers["save_reply_draft"],
            ),
            "save_task_proposal": ToolSpec(
                name="save_task_proposal",
                description="Create an in-memory task proposal only; never writes externally.",
                argument_model=SaveTaskProposalArgs,
                handler=handlers["save_task_proposal"],
            ),
            "ask_user": ToolSpec(
                name="ask_user",
                description="Pause for a human answer without performing an external action.",
                argument_model=AskUserArgs,
                handler=handlers["ask_user"],
            ),
            "done": ToolSpec(
                name="done",
                description="Mark the bounded Mock Tool loop complete.",
                argument_model=DoneArgs,
                handler=handlers["done"],
            ),
        }
        if enabled_tool_names is not None:
            enabled = set(enabled_tool_names)
            unknown = enabled.difference(self._specs)
            if unknown:
                raise ValueError("enabled_tool_names contains an unknown tool")
            self._specs = {
                name: spec for name, spec in self._specs.items() if name in enabled
            }
        self._execution_counts = {name: 0 for name in self._specs}

    def openai_tools(self) -> list[dict[str, object]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.argument_model.model_json_schema(),
                },
            }
            for spec in self._specs.values()
        ]

    def openai_tool_names(self) -> tuple[str, ...]:
        return tuple(self._specs)

    def validate_call(self, call: ToolCall) -> ValidatedToolCall:
        require_allowed_tool(call.name)
        if call.name not in self._specs:
            raise UnknownToolError("Tool was not exposed for this runtime context.")
        spec = self._specs[call.name]
        try:
            payload: Any = json.loads(call.arguments)
        except (TypeError, json.JSONDecodeError) as exc:
            raise InvalidToolArgumentsError(
                "Tool arguments are not valid JSON."
            ) from exc
        if not isinstance(payload, dict):
            raise InvalidToolArgumentsError("Tool arguments must be a JSON object.")
        try:
            arguments = spec.argument_model.model_validate(payload)
        except ValidationError as exc:
            raise InvalidToolArgumentsError(
                "Tool arguments failed schema or business validation."
            ) from exc
        return ValidatedToolCall(
            call=call,
            arguments=arguments,
            signature=f"{call.name}:{canonical_arguments(arguments)}",
            trace_arguments=trace_arguments(call.name, arguments),
        )

    def execute(self, call: ToolCall) -> ToolObservation:
        return self.execute_validated(self.validate_call(call), tool_call_id=call.id)

    def execute_validated(
        self,
        validated: ValidatedToolCall,
        *,
        tool_call_id: str,
    ) -> ToolObservation:
        spec = self._specs[validated.call.name]
        self._execution_counts[validated.call.name] += 1
        try:
            raw_observation = spec.handler(validated.arguments)
        except ToolError:
            raise
        except Exception as exc:
            raise ToolExecutionError("Mock Tool execution failed.") from exc
        try:
            observation = ToolObservation.model_validate(raw_observation)
        except ValidationError as exc:
            raise ObservationValidationError(
                "Tool observation failed validation."
            ) from exc
        if observation.tool_name != validated.call.name:
            raise ObservationValidationError(
                "Tool observation name did not match call."
            )
        if observation.tool_call_id not in (None, tool_call_id):
            raise ToolIdMismatchError("Tool observation ID did not match call.")
        return observation.model_copy(update={"tool_call_id": tool_call_id})

    def execution_count(self, name: str) -> int:
        return self._execution_counts.get(name, 0)
