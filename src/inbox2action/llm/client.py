from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import openai
from openai import OpenAI

from inbox2action.config import Settings
from inbox2action.errors import (
    ModelAuthenticationError,
    ModelEmptyResponseError,
    ModelError,
    ModelInvalidRequestError,
    ModelNotConfiguredError,
    ModelProtocolError,
    ModelRateLimitedError,
    ModelReasoningProtocolError,
    ModelTimeoutError,
    ModelUnavailableError,
)
from inbox2action.llm.models import ChatCompletionResult, ToolCall
from inbox2action.llm.protocols import ChatMessage


class OpenAIChatClient:
    """Small, injectable adapter around the native OpenAI SDK."""

    def __init__(
        self,
        settings: Settings,
        *,
        sdk_client_factory: Callable[..., Any] = OpenAI,
    ) -> None:
        self._settings = settings
        self._sdk_client: Any | None = None

        if settings.llm_enabled and settings.api_key_value is not None:
            self._sdk_client = sdk_client_factory(
                api_key=settings.api_key_value,
                base_url=settings.llm_base_url,
                timeout=settings.llm_timeout_seconds,
                max_retries=settings.llm_max_retries,
            )

    @property
    def is_configured(self) -> bool:
        return self._sdk_client is not None

    def __repr__(self) -> str:
        return (
            f"OpenAIChatClient(model={self._settings.llm_model_name!r}, "
            f"enabled={self._settings.llm_enabled}, "
            f"configured={self.is_configured})"
        )

    def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        response_format: Mapping[str, object] | None = None,
        tools: Sequence[Mapping[str, object]] | None = None,
    ) -> ChatCompletionResult:
        if self._sdk_client is None:
            raise ModelNotConfiguredError(
                "The model is disabled or its API key is not configured."
            )

        request: dict[str, Any] = {
            "model": self._settings.llm_model_name,
            "messages": list(messages),
            "max_tokens": self._settings.llm_max_tokens,
        }
        if response_format is not None:
            request["response_format"] = dict(response_format)
        if tools is not None:
            request["tools"] = [dict(tool) for tool in tools]
            request["tool_choice"] = "required"
        request["extra_body"] = {
            "thinking": {"type": self._settings.llm_thinking_mode}
        }

        try:
            response = self._sdk_client.chat.completions.create(**request)
        except Exception as exc:
            raise self._map_sdk_error(exc) from exc

        return self._normalize_response(response)

    @staticmethod
    def _map_sdk_error(error: Exception) -> ModelError:
        if isinstance(error, openai.AuthenticationError):
            return ModelAuthenticationError("Model authentication failed.")
        if isinstance(error, openai.APITimeoutError):
            return ModelTimeoutError("Model request timed out.")
        if isinstance(error, openai.RateLimitError):
            return ModelRateLimitedError("Model request was rate limited.")
        if isinstance(error, openai.APIConnectionError):
            return ModelUnavailableError("Model connection failed.")
        if isinstance(error, openai.BadRequestError):
            return ModelInvalidRequestError("Model rejected the request.")
        if isinstance(error, openai.InternalServerError):
            return ModelUnavailableError("Model service is unavailable.")
        if isinstance(error, openai.APIStatusError):
            status_code = getattr(error, "status_code", None)
            if status_code == 401:
                return ModelAuthenticationError("Model authentication failed.")
            if status_code == 429:
                return ModelRateLimitedError("Model request was rate limited.")
            if isinstance(status_code, int) and status_code >= 500:
                return ModelUnavailableError("Model service is unavailable.")
            return ModelInvalidRequestError("Model rejected the request.")
        return ModelProtocolError("The model SDK returned an unclassified error.")

    def _normalize_response(self, response: Any) -> ChatCompletionResult:
        if response is None:
            raise ModelEmptyResponseError("Model returned an empty response.")

        choices = getattr(response, "choices", None)
        if not choices:
            raise ModelEmptyResponseError("Model returned no choices.")

        choice = choices[0]
        message = getattr(choice, "message", None)
        if message is None:
            raise ModelProtocolError("Model response did not contain a message.")

        tool_calls = self._normalize_tool_calls(getattr(message, "tool_calls", None))
        reasoning_content = getattr(message, "reasoning_content", None)
        if reasoning_content is not None and not isinstance(reasoning_content, str):
            raise ModelReasoningProtocolError("Model reasoning content was not text.")
        if (
            self._settings.llm_thinking_mode == "enabled"
            and tool_calls
            and not reasoning_content
        ):
            raise ModelReasoningProtocolError(
                "Thinking-mode tool response omitted reasoning content."
            )
        content = getattr(message, "content", None)
        if not tool_calls and (
            content is None or (isinstance(content, str) and not content.strip())
        ):
            raise ModelEmptyResponseError("Model returned empty content.")
        if content is not None and not isinstance(content, str):
            raise ModelProtocolError("Model content was not text.")

        usage = getattr(response, "usage", None)
        return ChatCompletionResult(
            model=self._safe_model_name(getattr(response, "model", None)),
            content=content,
            finish_reason=self._safe_string(getattr(choice, "finish_reason", None)),
            prompt_tokens=self._safe_int(getattr(usage, "prompt_tokens", None)),
            completion_tokens=self._safe_int(getattr(usage, "completion_tokens", None)),
            total_tokens=self._safe_int(getattr(usage, "total_tokens", None)),
            tool_calls=tool_calls,
            reasoning_content=reasoning_content,
        )

    @staticmethod
    def _normalize_tool_calls(raw_tool_calls: Any) -> tuple[ToolCall, ...]:
        if raw_tool_calls is None:
            return ()
        if not isinstance(raw_tool_calls, (list, tuple)):
            raise ModelProtocolError("Model tool calls were not a list.")

        normalized: list[ToolCall] = []
        for raw_call in raw_tool_calls:
            call_id = getattr(raw_call, "id", None)
            function = getattr(raw_call, "function", None)
            name = getattr(function, "name", None)
            arguments = getattr(function, "arguments", None)
            if not isinstance(call_id, str) or not call_id:
                raise ModelProtocolError("Model tool call shape was invalid.")
            if not isinstance(name, str) or not name:
                raise ModelProtocolError("Model tool call shape was invalid.")
            if not isinstance(arguments, str) or not arguments:
                raise ModelProtocolError("Model tool call shape was invalid.")
            normalized.append(ToolCall(id=call_id, name=name, arguments=arguments))
        return tuple(normalized)

    def _safe_model_name(self, value: Any) -> str:
        return (
            value if isinstance(value, str) and value else self._settings.llm_model_name
        )

    @staticmethod
    def _safe_string(value: Any) -> str | None:
        return value if isinstance(value, str) else None

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        return value if isinstance(value, int) and not isinstance(value, bool) else None
