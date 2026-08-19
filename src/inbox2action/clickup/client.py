"""Small, read-only ClickUp API client with a replaceable HTTP boundary."""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import SecretStr

from .errors import (
    ClickUpAuthenticationError,
    ClickUpConfigurationError,
    ClickUpError,
    ClickUpForbiddenError,
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


class ClickUpClient:
    """Access only the ClickUp user and list-task GET endpoints."""

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
            summaries.append(ClickUpTask(task_id=task_id, name=name))
        return summaries

    def _get_json(self, path: str) -> object:
        request = Request(
            f"{API_BASE_URL}{path}",
            headers={
                "Accept": "application/json",
                "Authorization": self._api_token,
            },
            method="GET",
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
