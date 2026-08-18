"""Gmail API transport limited to the Inbox2Action readonly pilot boundary."""

from __future__ import annotations

import logging
from base64 import urlsafe_b64decode
from binascii import Error as Base64DecodeError
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
_MAX_BODY_LENGTH = 50_000
_MAX_HTML_LENGTH = 100_000
_MAX_MIME_DEPTH = 32
_MAX_MIME_PARTS = 128


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


@dataclass(frozen=True)
class GmailMessage:
    """Bounded message content used to construct a provider-neutral envelope."""

    message_id: str
    thread_id: str
    from_address: str
    reply_to: str
    subject: str
    date: str
    body: str
    html: str | None


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

    def read_message(
        self,
        message_id: str,
        *,
        thread_id: str | None = None,
    ) -> GmailMessage:
        """Read one bounded message body without exposing raw MIME downstream."""

        if not isinstance(message_id, str) or not message_id or len(message_id) > 256:
            raise ValueError("message_id must be a non-empty bounded string")
        service = self._build_service()

        def get_message() -> Any:
            return (
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )

        response = self._execute(get_message)
        return _full_message(response, message_id, thread_id)

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
    values = _header_values(headers)
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


def _full_message(
    response: Any,
    message_id: str,
    fallback_thread_id: str | None,
) -> GmailMessage:
    if not isinstance(response, dict):
        raise GmailApiResponseError()
    payload = response.get("payload")
    if not isinstance(payload, dict):
        raise GmailApiResponseError()
    headers = payload.get("headers", [])
    if not isinstance(headers, list):
        raise GmailApiResponseError()
    values = _header_values(headers)
    plain, html = _extract_body_parts(payload)
    if not plain and not html:
        snippet = response.get("snippet")
        if isinstance(snippet, str):
            plain = _safe_body(snippet, _MAX_BODY_LENGTH)
    if not plain and html:
        plain = html
    if not plain:
        raise GmailApiResponseError()

    response_message_id = response.get("id", message_id)
    response_thread_id = response.get("threadId", fallback_thread_id or "")
    if not isinstance(response_message_id, str) or not isinstance(
        response_thread_id, str
    ):
        raise GmailApiResponseError()
    return GmailMessage(
        message_id=_safe_text(response_message_id, 256),
        thread_id=_safe_text(response_thread_id, 256),
        from_address=_safe_text(values.get("from", ""), 320),
        reply_to=_safe_text(values.get("reply-to", ""), 320),
        subject=_safe_text(values.get("subject", ""), 200),
        date=_safe_text(values.get("date", ""), 64),
        body=_safe_body(plain, _MAX_BODY_LENGTH),
        html=_safe_body(html, _MAX_HTML_LENGTH) if html else None,
    )


def _header_values(headers: list[Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    for header in headers:
        if not isinstance(header, dict):
            continue
        name = header.get("name")
        value = header.get("value")
        if isinstance(name, str) and isinstance(value, str):
            values.setdefault(name.casefold(), value)
    return values


def _extract_body_parts(payload: dict[str, Any]) -> tuple[str, str]:
    plain_parts: list[str] = []
    html_parts: list[str] = []
    visited_parts = 0
    plain_length = 0
    html_length = 0

    def visit(part: Any, depth: int = 0) -> None:
        nonlocal html_length, plain_length, visited_parts
        if not isinstance(part, dict):
            return
        if depth > _MAX_MIME_DEPTH or visited_parts >= _MAX_MIME_PARTS:
            return
        visited_parts += 1
        mime_type = part.get("mimeType")
        if isinstance(mime_type, str):
            normalized_mime = mime_type.casefold()
            body = part.get("body")
            if isinstance(body, dict):
                data = body.get("data")
                if isinstance(data, str) and data:
                    if normalized_mime == "text/plain":
                        remaining = _MAX_BODY_LENGTH - plain_length
                        if remaining > 0:
                            decoded = _decode_body(data, remaining)
                            bounded = decoded[:remaining]
                            plain_parts.append(bounded)
                            plain_length += len(bounded)
                    elif normalized_mime == "text/html":
                        remaining = _MAX_HTML_LENGTH - html_length
                        if remaining > 0:
                            decoded = _decode_body(data, remaining)
                            bounded = decoded[:remaining]
                            html_parts.append(bounded)
                            html_length += len(bounded)
        children = part.get("parts", [])
        if isinstance(children, list):
            for child in children:
                visit(child, depth + 1)
                if visited_parts >= _MAX_MIME_PARTS:
                    break

    visit(payload)
    return (
        "\n".join(plain_parts)[:_MAX_BODY_LENGTH],
        "\n".join(html_parts)[:_MAX_HTML_LENGTH],
    )


def _decode_body(value: str, max_length: int) -> str:
    try:
        # Gmail may return a very large base64url field. Decode only the
        # bounded prefix needed by the downstream envelope; raw MIME never
        # needs to be materialized in memory in full.
        max_encoded_length = ((max_length * 4 + 2) // 3) + 4
        bounded = value
        if len(bounded) > max_encoded_length:
            bounded = bounded[:max_encoded_length]
            bounded = bounded[: len(bounded) - (len(bounded) % 4)]
        padded = bounded + "=" * (-len(bounded) % 4)
        return urlsafe_b64decode(padded.encode("ascii")).decode("utf-8", errors="replace")[:max_length]
    except (Base64DecodeError, UnicodeEncodeError, ValueError):
        raise GmailApiResponseError() from None


def _safe_body(value: str, limit: int) -> str:
    cleaned = "".join(
        " " if ord(character) < 32 and character not in "\n\t" or ord(character) == 127 else character
        for character in value
    )
    return cleaned.strip()[:limit]


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
    from googleapiclient.discovery import build  # type: ignore[import-not-found]

    return build("gmail", "v1", credentials=credentials, cache_discovery=False)
