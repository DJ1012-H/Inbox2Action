"""Small, read-only ClickUp API client with a replaceable HTTP boundary."""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from pydantic import SecretStr

from inbox2action.tools.schemas import CreateClickUpTaskArgs

from .errors import (
    ClickUpAuthenticationError,
    ClickUpConfigurationError,
    ClickUpError,
    ClickUpForbiddenError,
    ClickUpInvalidRequestError,
    ClickUpInvalidResponseError,
    ClickUpNotFoundError,
    ClickUpRateLimitedError,
    ClickUpTimeoutError,
    ClickUpUnavailableError,
)

API_BASE_URL = "https://api.clickup.com/api/v2"
_MAX_RESPONSE_BYTES = 1_048_576
_MAX_TASKS = 1_000
_MAX_FIELD_LENGTH = 512


class _RawResponse(Protocol):
    status: int

    def read(self, amount: int = ...) -> bytes:
        """Read at most the requested number of bytes."""

    def close(self) -> None:
        """Release the response resources."""


RequestExecutor = Callable[[Request, float], _RawResponse]


@dataclass(frozen=True)
class ClickUpUser:
    """The bounded user fields needed by the readonly smoke test."""

    user_id: str
    username: str


@dataclass(frozen=True)
class ClickUpTask:
    """A bounded task summary; descriptions and provider payloads are excluded."""

    task_id: str
    name: str
    url: str | None = None


@dataclass(frozen=True)
class ClickUpCustomField:
    """The bounded custom-field metadata needed by Stage 7."""

    field_id: str
    name: str
    field_type: str


@dataclass(frozen=True)
class ClickUpCreatedTask:
    """The minimum bounded response from a successful create call."""

    task_id: str
    url: str | None


class ClickUpClient:
    """Access the bounded ClickUp readonly and create-task endpoints."""

    def __init__(
        self,
        api_token: str | SecretStr,
        list_id: str,
        timeout_seconds: float = 10.0,
        *,
        request_executor: RequestExecutor | None = None,
    ) -> None:
        token = _secret_value(api_token)
        if token is None:
            raise ClickUpConfigurationError()
        normalized_list_id = _validate_list_id(list_id)
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(float(timeout_seconds))
            or not 0 < timeout_seconds <= 30
        ):
            raise ClickUpConfigurationError()

        self._api_token = token
        self._list_id = normalized_list_id
        self._timeout_seconds = float(timeout_seconds)
        self._request_executor = request_executor or _default_request_executor
        self._idempotency_field_id: str | None = None

    def get_authorized_user(self) -> ClickUpUser:
        """Return the bounded identity from GET /user."""

        payload = self._get_json("/user")
        if not isinstance(payload, dict):
            raise ClickUpInvalidResponseError()
        user = payload.get("user")
        if not isinstance(user, dict):
            raise ClickUpInvalidResponseError()
        user_id = _bounded_identifier(user.get("id"))
        username = _bounded_text(user.get("username"))
        if user_id is None or username is None:
            raise ClickUpInvalidResponseError()
        return ClickUpUser(user_id=user_id, username=username)

    def get_list_tasks(self, page: int = 0) -> list[ClickUpTask]:
        """Return bounded task summaries from one archived=false list page."""

        if isinstance(page, bool) or not isinstance(page, int) or page < 0:
            raise ClickUpConfigurationError()
        payload = self._get_json(
            f"/list/{self._list_id}/task?archived=false&page={page}"
        )
        if not isinstance(payload, dict):
            raise ClickUpInvalidResponseError()
        tasks = payload.get("tasks")
        if not isinstance(tasks, list) or len(tasks) > _MAX_TASKS:
            raise ClickUpInvalidResponseError()

        summaries: list[ClickUpTask] = []
        for task in tasks:
            if not isinstance(task, dict):
                raise ClickUpInvalidResponseError()
            task_id = _bounded_identifier(task.get("id"))
            name = _bounded_text(task.get("name"))
            if task_id is None or name is None:
                raise ClickUpInvalidResponseError()
            url = task.get("url")
            if url is not None and (
                not isinstance(url, str) or not _valid_task_url(url)
            ):
                url = None
            summaries.append(ClickUpTask(task_id=task_id, name=name, url=url))
        return summaries

    def get_list_custom_fields(self) -> list[ClickUpCustomField]:
        """Return bounded custom-field metadata from the configured List."""

        payload = self._get_json(f"/list/{self._list_id}/field")
        if not isinstance(payload, dict):
            raise ClickUpInvalidResponseError()
        fields = payload.get("fields")
        if not isinstance(fields, list) or len(fields) > _MAX_TASKS:
            raise ClickUpInvalidResponseError()

        result: list[ClickUpCustomField] = []
        for field in fields:
            if not isinstance(field, dict):
                raise ClickUpInvalidResponseError()
            field_id = _bounded_identifier(field.get("id"))
            name = _bounded_text(field.get("name"))
            field_type = _bounded_text(field.get("type"))
            if field_id is None or name is None or field_type is None:
                raise ClickUpInvalidResponseError()
            result.append(
                ClickUpCustomField(
                    field_id=field_id,
                    name=name,
                    field_type=field_type,
                )
            )
        return result

    def resolve_idempotency_field(self) -> str:
        """Discover and cache the unique text field used for Stage 7 idempotency."""

        if self._idempotency_field_id is not None:
            return self._idempotency_field_id
        matches = [
            field
            for field in self.get_list_custom_fields()
            if field.name == "Inbox2Action Key"
        ]
        if len(matches) != 1 or matches[0].field_type not in {"text", "short_text"}:
            raise ClickUpConfigurationError()
        self._idempotency_field_id = matches[0].field_id
        return matches[0].field_id

    def find_tasks_by_idempotency_key(self, idempotency_key: str) -> list[ClickUpTask]:
        """Find tasks by the exact Stage 7 custom-field marker."""

        field_id = self._idempotency_field_id
        if field_id is None:
            raise ClickUpConfigurationError()
        normalized_key = _bounded_text(idempotency_key)
        if normalized_key is None:
            raise ClickUpConfigurationError()
        custom_fields = json.dumps(
            [
                {
                    "field_id": field_id,
                    "operator": "==",
                    "value": normalized_key,
                }
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        payload = self._get_json(
            f"/list/{self._list_id}/task?archived=false&page=0&custom_fields="
            f"{quote(custom_fields, safe='')}"
        )
        if not isinstance(payload, dict):
            raise ClickUpInvalidResponseError()
        tasks = payload.get("tasks")
        if not isinstance(tasks, list) or len(tasks) > _MAX_TASKS:
            raise ClickUpInvalidResponseError()
        summaries: list[ClickUpTask] = []
        for task in tasks:
            if not isinstance(task, dict):
                raise ClickUpInvalidResponseError()
            task_id = _bounded_identifier(task.get("id"))
            name = _bounded_text(task.get("name"))
            if task_id is None or name is None:
                raise ClickUpInvalidResponseError()
            url = task.get("url")
            if url is not None and (
                not isinstance(url, str) or not _valid_task_url(url)
            ):
                url = None
            summaries.append(ClickUpTask(task_id=task_id, name=name, url=url))
        return summaries

    def create_task(
        self,
        *,
        title: str,
        description: str,
        due_at: datetime | str | None,
        priority: str,
        idempotency_key: str,
    ) -> ClickUpCreatedTask:
        """Create exactly one task from a validated task proposal."""

        field_id = self._idempotency_field_id
        if field_id is None:
            raise ClickUpConfigurationError()
        normalized_key = _bounded_text(idempotency_key)
        if normalized_key is None:
            raise ClickUpConfigurationError()

        try:
            proposal = CreateClickUpTaskArgs.model_validate(
                {
                    "title": title,
                    "description": description,
                    "due_at": due_at,
                    "priority": priority,
                }
            )
        except ValueError:
            raise ClickUpConfigurationError() from None

        body: dict[str, object] = {
            "name": proposal.title,
            "description": proposal.description,
            "priority": {"high": 2, "medium": 3, "low": 4}[proposal.priority],
            "custom_fields": [{"id": field_id, "value": normalized_key}],
        }
        if proposal.due_at is not None:
            body["due_date"] = _epoch_milliseconds(proposal.due_at)

        payload = self._request_json(
            f"/list/{self._list_id}/task",
            method="POST",
            body=body,
        )
        if not isinstance(payload, dict):
            raise ClickUpInvalidResponseError()
        task_id = _bounded_text(payload.get("id"))
        if task_id is None:
            raise ClickUpInvalidResponseError()
        url = payload.get("url")
        if url is not None and (not isinstance(url, str) or not _valid_task_url(url)):
            raise ClickUpInvalidResponseError()
        return ClickUpCreatedTask(task_id=task_id, url=url)

    def _get_json(self, path: str) -> object:
        return self._request_json(path, method="GET")

    def _request_json(
        self,
        path: str,
        *,
        method: str,
        body: dict[str, object] | None = None,
    ) -> object:
        encoded_body = (
            None
            if body is None
            else json.dumps(
                body,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        headers = {
            "Accept": "application/json",
            "Authorization": self._api_token,
        }
        if encoded_body is not None:
            headers["Content-Type"] = "application/json"
        request = Request(
            f"{API_BASE_URL}{path}",
            data=encoded_body,
            headers=headers,
            method=method,
        )
        try:
            response = self._request_executor(request, self._timeout_seconds)
        except HTTPError as error:
            raise _map_http_status(error.code) from None
        except TimeoutError:
            raise ClickUpTimeoutError() from None
        except URLError as error:
            if isinstance(error.reason, TimeoutError):
                raise ClickUpTimeoutError() from None
            raise ClickUpUnavailableError() from None
        except ClickUpError:
            raise
        except OSError:
            raise ClickUpUnavailableError() from None
        except Exception:  # noqa: BLE001 - the boundary exposes only safe provider codes
            raise ClickUpUnavailableError() from None

        try:
            status = _response_status(response)
            if not 200 <= status < 300:
                raise _map_http_status(status)
            raw_body = response.read(_MAX_RESPONSE_BYTES + 1)
            if not isinstance(raw_body, bytes) or len(raw_body) > _MAX_RESPONSE_BYTES:
                raise ClickUpInvalidResponseError()
        except ClickUpError:
            raise
        except TimeoutError:
            raise ClickUpTimeoutError() from None
        except OSError:
            raise ClickUpUnavailableError() from None
        except Exception:  # noqa: BLE001 - response details must not escape
            raise ClickUpInvalidResponseError() from None
        finally:
            with suppress(Exception):
                response.close()

        try:
            return json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ClickUpInvalidResponseError() from None


def _default_request_executor(request: Request, timeout: float) -> _RawResponse:
    return urlopen(request, timeout=timeout)


def _secret_value(value: str | SecretStr | object) -> str | None:
    if isinstance(value, SecretStr):
        token = value.get_secret_value()
    elif isinstance(value, str):
        token = value
    else:
        return None
    return token if token.strip() else None


def _validate_list_id(value: object) -> str:
    if not isinstance(value, str):
        raise ClickUpConfigurationError()
    normalized = value.strip()
    if not normalized or not normalized.isascii() or not normalized.isdigit():
        raise ClickUpConfigurationError()
    return normalized


def _response_status(response: _RawResponse) -> int:
    status = getattr(response, "status", None)
    if status is None:
        getcode = getattr(response, "getcode", None)
        status = getcode() if callable(getcode) else None
    if isinstance(status, bool) or not isinstance(status, int):
        raise ClickUpInvalidResponseError()
    return status


def _map_http_status(status: int) -> ClickUpError:
    if status == 400:
        return ClickUpInvalidRequestError()
    if status == 401:
        return ClickUpAuthenticationError()
    if status == 403:
        return ClickUpForbiddenError()
    if status == 404:
        return ClickUpNotFoundError()
    if status == 429:
        return ClickUpRateLimitedError()
    if 500 <= status <= 599:
        return ClickUpUnavailableError()
    return ClickUpInvalidResponseError()


def _bounded_identifier(value: object) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return None
    text = str(value).strip()
    if not text or len(text) > _MAX_FIELD_LENGTH:
        return None
    return _clean_text(text)


def _bounded_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = _clean_text(value.strip())
    if not text or len(text) > _MAX_FIELD_LENGTH:
        return None
    return text


def _clean_text(value: str) -> str:
    return "".join(
        " " if ord(character) < 32 or ord(character) == 127 else character
        for character in value
    )


def _epoch_milliseconds(value: datetime) -> int:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ClickUpConfigurationError()
    return int(value.timestamp() * 1000)


def _valid_task_url(value: str) -> bool:
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname == "app.clickup.com"
        and parsed.username is None
        and parsed.password is None
        and bool(parsed.path)
    )
