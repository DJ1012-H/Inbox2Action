from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from inbox2action.gmail import (
    GMAIL_READONLY_SCOPE,
    PILOT_QUERY,
    GmailApiAuthenticationError,
    GmailApiAuthorizationError,
    GmailApiNetworkError,
    GmailApiResponseError,
    GmailReadonlyTransport,
    GmailTokenInvalidError,
)


@dataclass
class FakeRequest:
    response: Any = None
    error: Exception | None = None

    def execute(self) -> Any:
        if self.error is not None:
            raise self.error
        return self.response


class FakeMessages:
    def __init__(self, pages: dict[str | None, dict[str, Any]], details: dict[str, dict[str, Any]]) -> None:
        self.pages = pages
        self.details = details
        self.list_calls: list[dict[str, Any]] = []
        self.get_calls: list[dict[str, Any]] = []

    def list(self, **kwargs: Any) -> FakeRequest:
        self.list_calls.append(kwargs)
        return FakeRequest(self.pages[kwargs.get("pageToken")])

    def get(self, **kwargs: Any) -> FakeRequest:
        self.get_calls.append(kwargs)
        return FakeRequest(self.details[kwargs["id"]])


class FakeUsers:
    def __init__(self, messages: FakeMessages) -> None:
        self.messages_resource = messages
        self.profile_calls: list[dict[str, Any]] = []

    def getProfile(self, **kwargs: Any) -> FakeRequest:
        self.profile_calls.append(kwargs)
        return FakeRequest({"emailAddress": "pilot@example.test"})

    def messages(self) -> FakeMessages:
        return self.messages_resource


class FakeService:
    def __init__(self, users: FakeUsers) -> None:
        self.users_resource = users

    def users(self) -> FakeUsers:
        return self.users_resource


def _service() -> tuple[FakeService, FakeMessages]:
    details = {
        "m1": {
            "id": "m1",
            "threadId": "t1",
            "payload": {
                "headers": [
                    {"name": "sUbJeCt", "value": "Subject 1"},
                    {"name": "FROM", "value": "sender@example.test"},
                    {"name": "Date", "value": "Wed, 13 Aug 2026 10:00:00 +0800"},
                ]
            },
        },
        "m2": {
            "id": "m2",
            "threadId": "t2",
            "payload": {"headers": []},
        },
        "m3": {
            "id": "m3",
            "threadId": "t3",
            "payload": {"headers": []},
        },
    }
    messages = FakeMessages(
        {
            None: {
                "messages": [{"id": "m1", "threadId": "t1"}, {"id": "m2", "threadId": "t2"}],
                "nextPageToken": "page-2",
            },
            "page-2": {
                "messages": [{"id": "m2", "threadId": "t2"}, {"id": "m3", "threadId": "t3"}],
                "nextPageToken": "page-3",
            },
        },
        details,
    )
    users = FakeUsers(messages)
    return FakeService(users), messages


def test_profile_and_messages_use_only_bounded_metadata_calls() -> None:
    service, messages = _service()
    credentials = SimpleNamespace(scopes=[GMAIL_READONLY_SCOPE])
    factory_calls: list[object] = []
    transport = GmailReadonlyTransport(
        lambda: credentials,
        service_factory=lambda value: factory_calls.append(value) or service,
    )

    profile = transport.get_profile()
    summaries = transport.read_recent_messages(20)

    assert profile.email_address == "pilot@example.test"
    assert [summary.message_id for summary in summaries] == ["m1", "m2", "m3"]
    assert summaries[0].from_address == "sender@example.test"
    assert summaries[0].subject == "Subject 1"
    assert summaries[0].date.startswith("Wed, 13 Aug 2026")
    assert len(factory_calls) == 2
    assert len(messages.list_calls) == 2
    assert messages.list_calls[0] == {
        "userId": "me",
        "q": PILOT_QUERY,
        "maxResults": 10,
    }
    assert messages.list_calls[1]["pageToken"] == "page-2"
    assert all(call["format"] == "metadata" for call in messages.get_calls)
    assert all(call["metadataHeaders"] == ["From", "Subject", "Date"] for call in messages.get_calls)


def test_empty_recent_window_returns_no_messages_without_custom_label() -> None:
    messages = FakeMessages({None: {"messages": []}}, {})
    users = FakeUsers(messages)
    transport = GmailReadonlyTransport(
        lambda: object(), service_factory=lambda _credentials: FakeService(users)
    )

    assert transport.read_recent_messages() == []
    assert messages.list_calls == [
        {"userId": "me", "q": PILOT_QUERY, "maxResults": 10}
    ]


def test_incomplete_oauth_does_not_construct_gmail_service() -> None:
    calls: list[str] = []

    def fail_credentials() -> object:
        raise GmailTokenInvalidError()

    def service_factory(_credentials: object) -> object:
        calls.append("service")
        return object()

    transport = GmailReadonlyTransport(fail_credentials, service_factory=service_factory)
    with pytest.raises(GmailTokenInvalidError):
        transport.get_profile()
    assert calls == []


class HttpFailure(Exception):
    def __init__(self, status: int) -> None:
        self.resp = SimpleNamespace(status=status)


@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        (401, GmailApiAuthenticationError),
        (403, GmailApiAuthorizationError),
        (429, GmailApiNetworkError),
        (500, GmailApiNetworkError),
        (400, GmailApiResponseError),
    ],
)
def test_api_failure_types_are_distinguished(status: int, error_type: type[Exception]) -> None:
    messages = FakeMessages({None: {"messages": []}}, {})
    messages.list = lambda **kwargs: FakeRequest(error=HttpFailure(status))  # type: ignore[method-assign]
    users = FakeUsers(messages)
    transport = GmailReadonlyTransport(
        lambda: object(), service_factory=lambda _credentials: FakeService(users)
    )

    with pytest.raises(error_type):
        transport.read_recent_messages()
