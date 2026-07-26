from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import Protocol

from inbox2action.llm.models import ChatCompletionResult
from inbox2action.tools.mock_tools import DraftProposal, ToolObservation
from inbox2action.tools.policy import ToolError
from inbox2action.tools.registry import ToolRegistry, ValidatedToolCall


@dataclass(frozen=True)
class ToolTraceEntry:
    step: int
    tool_name: str
    validated_arguments: Mapping[str, object]
    observation_type: str
    status: str
    latency_ms: float


class ToolLoopError(Exception):
    """Safe control-flow error for a bounded tool loop."""

    def __init__(
        self,
        message: str,
        *,
        trace: Sequence[ToolTraceEntry] = (),
    ) -> None:
        super().__init__(message)
        self.trace = tuple(trace)


class ToolLoopLimitError(ToolLoopError):
    """The hard maximum number of tool steps was reached."""


class DuplicateToolCallError(ToolLoopError):
    """The model repeated the same tool and validated arguments."""


class ToolLoopProtocolError(ToolLoopError):
    """The model returned an unsupported tool-loop shape."""


class EmptyModelResponseError(ToolLoopError):
    """The model returned neither text nor a tool call."""


class CompletionWithoutDoneError(ToolLoopError):
    """The model returned final text without invoking the done control tool."""


class ReplanningRequiredError(ToolLoopError):
    """A calendar conflict must be replanned before completion."""


class RequiredToolNotCalledError(ToolLoopError):
    """A configured prerequisite read tool was skipped before completion."""


class UnsafeCompletionClaimError(ToolLoopError):
    """The completion text claimed an unsupported external side effect."""


class ToolCapableModel(Protocol):
    def complete(
        self,
        messages: Sequence[Mapping[str, object]],
        *,
        response_format: Mapping[str, object] | None = None,
        tools: Sequence[Mapping[str, object]] | None = None,
    ) -> ChatCompletionResult:
        """Return a normalized model response with optional tool calls."""


@dataclass(frozen=True)
class ToolLoopResult:
    last_response: ChatCompletionResult
    trace: tuple[ToolTraceEntry, ...]
    completed: bool
    proposals: tuple[DraftProposal, ...]


class ToolLoop:
    """Execute only validated allowlisted Mock Tools with a hard step cap."""

    def __init__(
        self,
        model: ToolCapableModel,
        registry: ToolRegistry,
        *,
        max_tool_steps: int = 6,
        required_tools_before_done: Sequence[str] = (),
        validated_call_observer: Callable[[int, ValidatedToolCall], None] | None = None,
    ) -> None:
        if max_tool_steps <= 0 or max_tool_steps > 20:
            raise ValueError("max_tool_steps must be between 1 and 20")
        allowed_names = set(registry.openai_tool_names())
        required_tools = frozenset(required_tools_before_done)
        if not required_tools.issubset(allowed_names):
            raise ValueError("required_tools_before_done contains an unknown tool")
        self._model = model
        self._registry = registry
        self._max_tool_steps = max_tool_steps
        self._required_tools_before_done = required_tools
        self._validated_call_observer = validated_call_observer

    def run(self, initial_messages: Sequence[Mapping[str, object]]) -> ToolLoopResult:
        messages: list[dict[str, object]] = [
            dict(message) for message in initial_messages
        ]
        trace: list[ToolTraceEntry] = []
        seen_call_ids: set[str] = set()
        executed_tool_names: set[str] = set()
        previous_signature: str | None = None
        conflict_signature: str | None = None

        for step in range(1, self._max_tool_steps + 1):
            response = self._model.complete(
                messages,
                tools=self._registry.openai_tools(),
            )
            if not response.tool_calls:
                if response.content and response.content.strip():
                    raise CompletionWithoutDoneError(
                        "Model returned text without calling done.",
                        trace=trace,
                    )
                raise EmptyModelResponseError(
                    "Model returned neither text nor a tool call.",
                    trace=trace,
                )
            if len(response.tool_calls) != 1:
                raise ToolLoopProtocolError(
                    "Exactly one tool call is required per model turn.",
                    trace=trace,
                )

            call = response.tool_calls[0]
            if not call.id or call.id in seen_call_ids:
                raise ToolLoopProtocolError(
                    "Tool call ID was missing or already used.",
                    trace=trace,
                )

            try:
                validated = self._registry.validate_call(call)
            except ToolError as exc:
                trace.append(self._rejected_trace(step, call.name))
                exc.trace = tuple(trace)
                raise

            if previous_signature == validated.signature:
                trace.append(self._rejected_trace(step, call.name, validated))
                raise DuplicateToolCallError(
                    "The same tool and validated arguments were repeated.",
                    trace=trace,
                )
            if conflict_signature is not None:
                if call.name == "done":
                    trace.append(self._rejected_trace(step, call.name, validated))
                    raise ReplanningRequiredError(
                        "A calendar conflict requires a new query or ask_user before done.",
                        trace=trace,
                    )
                if (
                    call.name == "check_calendar_availability"
                    and validated.signature == conflict_signature
                ):
                    trace.append(self._rejected_trace(step, call.name, validated))
                    raise DuplicateToolCallError(
                        "The conflicting calendar interval was queried again.",
                        trace=trace,
                    )

            if call.name == "done":
                missing_tools = self._required_tools_before_done - executed_tool_names
                if missing_tools:
                    trace.append(self._rejected_trace(step, call.name, validated))
                    raise RequiredToolNotCalledError(
                        "Required read tool was skipped before done.",
                        trace=trace,
                    )
                if self._claims_unsupported_external_write(validated.arguments):
                    trace.append(self._rejected_trace(step, call.name, validated))
                    raise UnsafeCompletionClaimError(
                        "Completion text claimed an unsupported external write.",
                        trace=trace,
                    )

            if self._validated_call_observer is not None:
                self._validated_call_observer(step, validated)

            started = perf_counter()
            try:
                observation = self._registry.execute_validated(
                    validated,
                    tool_call_id=call.id,
                )
            except ToolError as exc:
                trace.append(self._error_trace(step, call.name, validated, started))
                exc.trace = tuple(trace)
                raise
            latency_ms = round((perf_counter() - started) * 1000, 3)
            trace.append(
                ToolTraceEntry(
                    step=step,
                    tool_name=call.name,
                    validated_arguments=validated.trace_arguments,
                    observation_type=observation.observation_type,
                    status=observation.status,
                    latency_ms=latency_ms,
                )
            )

            seen_call_ids.add(call.id)
            executed_tool_names.add(call.name)
            previous_signature = validated.signature
            messages.append(self._assistant_message(response))
            messages.append(self._tool_message(observation))

            if observation.status == "conflict":
                conflict_signature = validated.signature
            elif conflict_signature is not None and call.name in {
                "ask_user",
                "check_calendar_availability",
            }:
                conflict_signature = None

            if call.name == "done":
                return ToolLoopResult(
                    last_response=response,
                    trace=tuple(trace),
                    completed=True,
                    proposals=tuple(self._registry.runtime.proposals),
                )
            if step == self._max_tool_steps:
                raise ToolLoopLimitError(
                    "MAX_TOOL_STEPS was reached before done.",
                    trace=trace,
                )

        raise ToolLoopLimitError("MAX_TOOL_STEPS was reached before done.", trace=trace)

    @staticmethod
    def _claims_unsupported_external_write(arguments: object) -> bool:
        summary = getattr(arguments, "summary", "")
        if not isinstance(summary, str):
            return False
        normalized = " ".join(summary.casefold().split())
        forbidden_claims = (
            "已创建日历事件",
            "已创建 calendar event",
            "calendar event created",
            "created a calendar event",
            "event has been created",
        )
        return any(claim in normalized for claim in forbidden_claims)

    @staticmethod
    def _assistant_message(response: ChatCompletionResult) -> dict[str, object]:
        message: dict[str, object] = {
            "role": "assistant",
            "content": response.content,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": call.arguments,
                    },
                }
                for call in response.tool_calls
            ],
        }
        if response.reasoning_content is not None:
            message["reasoning_content"] = response.reasoning_content
        return message

    @staticmethod
    def _tool_message(observation: ToolObservation) -> dict[str, object]:
        return {
            "role": "tool",
            "tool_call_id": observation.tool_call_id,
            "content": json.dumps(
                observation.model_dump(mode="json"),
                ensure_ascii=False,
            ),
        }

    @staticmethod
    def _rejected_trace(
        step: int,
        tool_name: str,
        validated: ValidatedToolCall | None = None,
    ) -> ToolTraceEntry:
        return ToolTraceEntry(
            step=step,
            tool_name=tool_name,
            validated_arguments=(validated.trace_arguments if validated else {}),
            observation_type="error",
            status="rejected",
            latency_ms=0.0,
        )

    @staticmethod
    def _error_trace(
        step: int,
        tool_name: str,
        validated: ValidatedToolCall,
        started: float,
    ) -> ToolTraceEntry:
        return ToolTraceEntry(
            step=step,
            tool_name=tool_name,
            validated_arguments=validated.trace_arguments,
            observation_type="error",
            status="error",
            latency_ms=round((perf_counter() - started) * 1000, 3),
        )
