"""Gmail API transport limited to the Inbox2Action readonly pilot boundary."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .errors import (
    GmailApiAuthenticationError,
    GmailApiAuthorizationError,
    GmailApiNetworkError,
    GmailApiResponseError,
    GmailError,
)

logger = logging.getLogger(__name__)

PILOT_QUERY = "newer_than:30d"
PILOT_MAX_MESSAGES = 20
PILOT_PAGE_SIZE = 10
PILOT_MAX_PAGES = 2
_METADATA_HEADERS = ["From", "Subject", "Date"]
_MAX_OUTPUT_FIELD_LENGTH = 2000


@dataclass(frozen=True)
class GmailProfile:
    """The bounded profile field used by the smoke test."""

    email_address: str


@dataclass(frozen=True)
class GmailMessageSummary:
    """Metadata-only Gmail message summary; it contains no body or attachment."""

    message_id: str
    thread_id: str
    from_address: str
    subject: str
    date: str


class GmailReadonlyTransport:
    """Read recent Gmail metadata through bounded readonly API calls."""

    def __init__(
        self,
        credential_provider: Callable[[], Any],
        *,
        service_factory: Callable[[Any], Any] | None = None,
    ) -> None:
        self._credential_provider = credential_provider
        self._service_factory = service_factory or _default_service_factory

    def get_profile(self) -> GmailProfile:
        service = self._build_service()
        response = self._execute(
            lambda: service.users().getProfile(userId="me").execute()
        )
        if not isinstance(response, dict):
            raise GmailApiResponseError()
        email_address = response.get("emailAddress")
        if not isinstance(email_address, str):
            raise GmailApiResponseError()
        return GmailProfile(email_address=_safe_text(email_address, 320))

    def read_recent_messages(self, max_messages: int = 10) -> list[GmailMessageSummary]:
        if isinstance(max_messages, bool) or not isinstance(max_messages, int):
            raise TypeError("max_messages must be an integer")
        if not 1 <= max_messages <= PILOT_MAX_MESSAGES:
            raise ValueError(f"max_messages must be between 1 and {PILOT_MAX_MESSAGES}")

        service = self._build_service()
        message_refs = self._list_message_refs(service, max_messages)
        summaries: list[GmailMessageSummary] = []
        for message_ref in message_refs:
            message_id = message_ref["id"]
            def get_message(message_id: str = message_id) -> Any:
                return (
                    service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=message_id,
                        format="metadata",
                        metadataHeaders=_METADATA_HEADERS,
                    )
                    .execute()
                )
            response = self._execute(get_message)
            summaries.append(_message_summary(response, message_ref))
        logger.info("gmail_readonly_messages_loaded")
        return summaries

    def _build_service(self) -> Any:
        # Credentials are deliberately resolved before building the API client.
        # This makes an incomplete OAuth flow fail closed without a Gmail call.
        credentials = self._credential_provider()
        try:
            return self._service_factory(credentials)
        except GmailError:
            raise
        except Exception:  # noqa: BLE001 - service construction becomes a safe API code
            raise GmailApiNetworkError() from None

    def _list_message_refs(
        self,
        service: Any,
        max_messages: int,
    ) -> list[dict[str, str]]:
        refs: list[dict[str, str]] = []
        seen_ids: set[str] = set()
        seen_page_tokens: set[str] = set()
        page_token: str | None = None

        for _ in range(PILOT_MAX_PAGES):
            request_kwargs: dict[str, Any] = {
                "userId": "me",
                "q": PILOT_QUERY,
                "maxResults": min(PILOT_PAGE_SIZE, max_messages - len(refs)),
            }
            if page_token is not None:
                request_kwargs["pageToken"] = page_token
            def list_messages(request_kwargs: dict[str, Any] = request_kwargs) -> Any:
                return service.users().messages().list(**request_kwargs).execute()

            response = self._execute(list_messages)
            if not isinstance(response, dict):
                raise GmailApiResponseError()
            messages = response.get("messages", [])
            if not isinstance(messages, list):
                raise GmailApiResponseError()
            for message in messages:
                if not isinstance(message, dict):
                    raise GmailApiResponseError()
                message_id = message.get("id")
                if not isinstance(message_id, str) or not message_id:
                    raise GmailApiResponseError()
                if message_id in seen_ids:
                    continue
                seen_ids.add(message_id)
                refs.append(
                    {
                        "id": message_id,
                        "thread_id": message.get("threadId", "")
                        if isinstance(message.get("threadId", ""), str)
                        else "",
                    }
                )
                if len(refs) >= max_messages:
                    return refs

            next_page_token = response.get("nextPageToken")
            if not isinstance(next_page_token, str) or not next_page_token:
                break
            if next_page_token in seen_page_tokens or next_page_token == page_token:
                break
            seen_page_tokens.add(next_page_token)
            page_token = next_page_token
        return refs

    @staticmethod
    def _execute(operation: Callable[[], Any]) -> Any:
        try:
            return operation()
        except GmailError:
            raise
        except Exception as exc:  # noqa: BLE001 - API errors are mapped below
            raise _map_api_exception(exc) from None


def _message_summary(response: Any, message_ref: dict[str, str]) -> GmailMessageSummary:
    if not isinstance(response, dict):
        raise GmailApiResponseError()
    payload = response.get("payload")
    if not isinstance(payload, dict):
        raise GmailApiResponseError()
    headers = payload.get("headers", [])
    if not isinstance(headers, list):
        raise GmailApiResponseError()
    values: dict[str, str] = {}
    for header in headers:
        if not isinstance(header, dict):
            continue
        name = header.get("name")
        value = header.get("value")
        if isinstance(name, str) and isinstance(value, str):
            values.setdefault(name.casefold(), value)
    message_id = response.get("id", message_ref["id"])
    thread_id = response.get("threadId", message_ref["thread_id"])
    if not isinstance(message_id, str) or not isinstance(thread_id, str):
        raise GmailApiResponseError()
    return GmailMessageSummary(
        message_id=_safe_text(message_id),
        thread_id=_safe_text(thread_id),
        from_address=_safe_text(values.get("from", "")),
        subject=_safe_text(values.get("subject", "")),
        date=_safe_text(values.get("date", "")),
    )


def _safe_text(value: str, limit: int = _MAX_OUTPUT_FIELD_LENGTH) -> str:
    cleaned = "".join(" " if ord(character) < 32 or ord(character) == 127 else character for character in value)
    return cleaned.strip()[:limit]


def _map_api_exception(error: Exception) -> GmailError:
    status = getattr(getattr(error, "resp", None), "status", None)
    if isinstance(status, str) and status.isdigit():
        status = int(status)
    if status == 401:
        return GmailApiAuthenticationError()
    if status == 403:
        return GmailApiAuthorizationError()
    if status == 429 or isinstance(status, int) and status >= 500:
        return GmailApiNetworkError()
    if status is not None:
        return GmailApiResponseError()
    return GmailApiNetworkError()


def _default_service_factory(credentials: Any) -> Any:
    from googleapiclient.discovery import build  # type: ignore[import-untyped]

    return build("gmail", "v1", credentials=credentials, cache_discovery=False)
