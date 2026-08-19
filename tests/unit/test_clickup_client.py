from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from inbox2action.clickup import (
    ClickUpAuthenticationError,
    ClickUpClient,
    ClickUpConfigurationError,
    ClickUpError,
    ClickUpForbiddenError,
    ClickUpInvalidResponseError,
    ClickUpNotFoundError,
    ClickUpRateLimitedError,
    ClickUpTimeoutError,
    ClickUpUnavailableError,
)


@dataclass
class FakeResponse:
    body: bytes
    status: int = 200
    closed: bool = False

    def read(self, amount: int = 0) -> bytes:
        assert amount == 1_048_577
        return self.body

    def close(self) -> None:
        self.closed = True


def make_client(
    payload: object,
    *,
    status: int = 200,
    token: str = "cu-test-secret",
    calls: list[tuple[Any, float]] | None = None,
) -> tuple[ClickUpClient, FakeResponse]:
    response = FakeResponse(json.dumps(payload).encode("utf-8"))

    def execute(request: Any, timeout: float) -> FakeResponse:
        if calls is not None:
            calls.append((request, timeout))
        return response

    response.status = status
    return (
        ClickUpClient(
            api_token=token,
            list_id="123456",
            timeout_seconds=7,
            request_executor=execute,
        ),
        response,
    )


def test_authorized_user_is_parsed_and_request_is_fixed_https_get() -> None:
    calls: list[tuple[Any, float]] = []
    client, response = make_client(
        {"user": {"id": 42, "username": "pilot-user"}}, calls=calls
    )

    user = client.get_authorized_user()

    request, timeout = calls[0]
    assert user.user_id == "42"
    assert user.username == "pilot-user"
    assert request.full_url == "https://api.clickup.com/api/v2/user"
    assert request.method == "GET"
    assert request.get_header("Authorization") == "cu-test-secret"
    assert request.get_header("Accept") == "application/json"
    assert timeout == 7
    assert response.closed is True


def test_list_tasks_is_parsed_without_retaining_descriptions() -> None:
    calls: list[tuple[Any, float]] = []
    client, _ = make_client(
        {
            "tasks": [
                {"id": "task-1", "name": "Prepare brief", "description": "secret"},
                {"id": "task-2", "name": "Review brief"},
            ]
        },
        calls=calls,
    )

    tasks = client.get_list_tasks(page=2)

    assert [(task.task_id, task.name) for task in tasks] == [
        ("task-1", "Prepare brief"),
        ("task-2", "Review brief"),
    ]
    assert calls[0][0].full_url == (
        "https://api.clickup.com/api/v2/list/123456/task?archived=false&page=2"
    )
    assert calls[0][0].method == "GET"
    assert all("description" not in task.__dict__ for task in tasks)


@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        (401, ClickUpAuthenticationError),
        (403, ClickUpForbiddenError),
        (404, ClickUpNotFoundError),
        (429, ClickUpRateLimitedError),
        (500, ClickUpUnavailableError),
        (503, ClickUpUnavailableError),
    ],
)
def test_http_statuses_are_classified_without_provider_body(
    status: int, error_type: type[ClickUpError]
) -> None:
    client, _ = make_client({"error": "provider secret body"}, status=status)

    with pytest.raises(error_type) as raised:
        client.get_authorized_user()

    assert raised.value.code in {
        "authentication",
        "forbidden",
        "not_found",
        "rate_limited",
        "unavailable",
    }
    assert "provider secret body" not in str(raised.value)


def test_timeout_is_classified() -> None:
    def timeout(_request: Any, _timeout: float) -> FakeResponse:
        raise TimeoutError()

    client = ClickUpClient(
        api_token="cu-test-secret",
        list_id="123456",
        request_executor=timeout,
    )

    with pytest.raises(ClickUpTimeoutError):
        client.get_authorized_user()


def test_non_json_response_is_invalid_response() -> None:
    response = FakeResponse(b"not-json")

    def execute(_request: Any, _timeout: float) -> FakeResponse:
        return response

    client = ClickUpClient("cu-test-secret", "123456", request_executor=execute)

    with pytest.raises(ClickUpInvalidResponseError):
        client.get_authorized_user()


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"user": []},
        {"user": {"id": 1}},
        {"tasks": [{"id": "task-1"}]},
    ],
)
def test_invalid_json_shapes_are_rejected(payload: object) -> None:
    client, _ = make_client(payload)

    with pytest.raises(ClickUpInvalidResponseError):
        if "tasks" in payload if isinstance(payload, dict) else False:
            client.get_list_tasks()
        else:
            client.get_authorized_user()


@pytest.mark.parametrize(
    ("api_token", "list_id", "page"),
    [("", "123456", 0), ("cu-token", "", 0), ("cu-token", "abc", 0), ("cu-token", "123456", -1)],
)
def test_invalid_client_inputs_fail_closed(
    api_token: str, list_id: str, page: int
) -> None:
    if api_token == "" or list_id != "123456":
        with pytest.raises(ClickUpConfigurationError):
            ClickUpClient(api_token, list_id)
        return

    client, _ = make_client({"tasks": []})
    with pytest.raises(ClickUpConfigurationError):
        client.get_list_tasks(page=page)


def test_error_text_and_repr_never_contain_token() -> None:
    token = "cu-super-secret-value"
    client, _ = make_client({}, status=401, token=token)

    with pytest.raises(ClickUpAuthenticationError) as raised:
        client.get_authorized_user()

    assert token not in str(raised.value)
    assert token not in repr(raised.value)
