from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import openai
import pytest

from inbox2action.config import Settings
from inbox2action.errors import (
    ModelAuthenticationError,
    ModelEmptyResponseError,
    ModelInvalidRequestError,
    ModelNotConfiguredError,
    ModelProtocolError,
    ModelRateLimitedError,
    ModelReasoningProtocolError,
    ModelTimeoutError,
    ModelUnavailableError,
)
from inbox2action.llm.client import OpenAIChatClient


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "llm_enabled": True,
        "llm_api_key": "placeholder-value-only",
        "llm_base_url": "https://api.deepseek.com",
        "llm_model_name": "deepseek-v4-flash",
        "llm_thinking_mode": "disabled",
        "llm_timeout_seconds": 30,
        "llm_max_retries": 0,
        "llm_max_tokens": 2048,
        "llm_max_tool_steps": 6,
    }
    values.update(overrides)
    return Settings(**values)


class FakeCompletions:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def create(self, **request: Any) -> Any:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return self.response


class FakeSdkClient:
    def __init__(self, completions: FakeCompletions) -> None:
        self.chat = SimpleNamespace(completions=completions)


def successful_response() -> Any:
    return SimpleNamespace(
        model="deepseek-v4-flash",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="中文测试响应"),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=3, completion_tokens=4, total_tokens=7),
    )


def sdk_response() -> Any:
    return SimpleNamespace(request=object(), status_code=401, headers={})


def test_disabled_model_never_constructs_sdk_or_calls_network() -> None:
    factory_calls: list[dict[str, Any]] = []

    def factory(**kwargs: Any) -> FakeSdkClient:
        factory_calls.append(kwargs)
        return FakeSdkClient(FakeCompletions())

    client = OpenAIChatClient(settings(llm_enabled=False), sdk_client_factory=factory)

    assert factory_calls == []
    assert client.is_configured is False
    with pytest.raises(ModelNotConfiguredError):
        client.complete([{"role": "user", "content": "test"}])


def test_missing_key_never_constructs_sdk_or_calls_network() -> None:
    factory_calls: list[dict[str, Any]] = []

    def factory(**kwargs: Any) -> FakeSdkClient:
        factory_calls.append(kwargs)
        return FakeSdkClient(FakeCompletions())

    client = OpenAIChatClient(
        settings(llm_api_key=None),
        sdk_client_factory=factory,
    )

    assert factory_calls == []
    with pytest.raises(ModelNotConfiguredError):
        client.complete([{"role": "user", "content": "test"}])


def test_successful_response_is_normalized_without_sdk_object_leak() -> None:
    completions = FakeCompletions(successful_response())
    client = OpenAIChatClient(
        settings(),
        sdk_client_factory=lambda **_: FakeSdkClient(completions),
    )

    result = client.complete(
        [{"role": "user", "content": "test"}],
        response_format={"type": "json_object"},
    )

    assert result.content == "中文测试响应"
    assert result.total_tokens == 7
    assert completions.calls[0]["model"] == "deepseek-v4-flash"
    assert completions.calls[0]["response_format"] == {"type": "json_object"}
    assert completions.calls[0]["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "api_key" not in completions.calls[0]


def test_thinking_mode_requires_reasoning_for_tool_calls_and_sends_enabled_flag() -> (
    None
):
    response = SimpleNamespace(
        model="deepseek-v4-flash",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="call-1",
                            function=SimpleNamespace(
                                name="get_current_time",
                                arguments="{}",
                            ),
                        )
                    ],
                    reasoning_content="private reasoning",
                ),
                finish_reason="tool_calls",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )
    completions = FakeCompletions(response=response)
    client = OpenAIChatClient(
        settings(llm_thinking_mode="enabled"),
        sdk_client_factory=lambda **_: FakeSdkClient(completions),
    )

    result = client.complete([{"role": "user", "content": "test"}])

    assert result.reasoning_present is True
    assert result.reasoning_length == len("private reasoning")
    assert result.reasoning_sha256 is not None
    assert completions.calls[0]["extra_body"] == {"thinking": {"type": "enabled"}}


def test_tool_loop_requests_require_a_tool_call() -> None:
    response = SimpleNamespace(
        model="deepseek-v4-flash",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="call-1",
                            function=SimpleNamespace(name="done", arguments='{"summary":"ok"}'),
                        )
                    ],
                    reasoning_content=None,
                ),
                finish_reason="tool_calls",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )
    completions = FakeCompletions(response=response)
    client = OpenAIChatClient(
        settings(), sdk_client_factory=lambda **_: FakeSdkClient(completions)
    )

    client.complete(
        [{"role": "user", "content": "test"}],
        tools=[{"type": "function", "function": {"name": "done"}}],
    )

    assert completions.calls[0]["tool_choice"] == "required"


def test_thinking_mode_rejects_tool_call_without_reasoning_content() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="call-1",
                            function=SimpleNamespace(name="done", arguments="{}"),
                        )
                    ],
                ),
                finish_reason="tool_calls",
            )
        ]
    )
    client = OpenAIChatClient(
        settings(llm_thinking_mode="enabled"),
        sdk_client_factory=lambda **_: FakeSdkClient(FakeCompletions(response)),
    )

    with pytest.raises(ModelReasoningProtocolError):
        client.complete([{"role": "user", "content": "test"}])


@pytest.mark.parametrize(
    "error,expected",
    [
        (
            openai.AuthenticationError(
                "placeholder", response=sdk_response(), body=None
            ),
            ModelAuthenticationError,
        ),
        (
            openai.APITimeoutError(request=object()),
            ModelTimeoutError,
        ),
        (
            openai.RateLimitError("placeholder", response=sdk_response(), body=None),
            ModelRateLimitedError,
        ),
        (
            openai.APIConnectionError(request=object()),
            ModelUnavailableError,
        ),
        (
            openai.BadRequestError("placeholder", response=sdk_response(), body=None),
            ModelInvalidRequestError,
        ),
    ],
)
def test_sdk_errors_are_mapped_without_leaking_exception_text(
    error: Exception,
    expected: type[Exception],
) -> None:
    completions = FakeCompletions(error=error)
    client = OpenAIChatClient(
        settings(),
        sdk_client_factory=lambda **_: FakeSdkClient(completions),
    )

    with pytest.raises(expected) as captured:
        client.complete([{"role": "user", "content": "test"}])

    assert "placeholder" not in str(captured.value)


@pytest.mark.parametrize(
    "response,expected",
    [
        (SimpleNamespace(choices=[]), ModelEmptyResponseError),
        (
            SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=""))]
            ),
            ModelEmptyResponseError,
        ),
        (SimpleNamespace(choices=[SimpleNamespace(message=None)]), ModelProtocolError),
        (
            SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=object()))]
            ),
            ModelProtocolError,
        ),
    ],
)
def test_malformed_sdk_responses_are_rejected(
    response: Any,
    expected: type[Exception],
) -> None:
    completions = FakeCompletions(response=response)
    client = OpenAIChatClient(
        settings(),
        sdk_client_factory=lambda **_: FakeSdkClient(completions),
    )

    with pytest.raises(expected):
        client.complete([{"role": "user", "content": "test"}])
