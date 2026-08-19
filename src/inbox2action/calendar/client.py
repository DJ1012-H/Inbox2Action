"""Small injectable Google Calendar API client."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .errors import (
    GoogleCalendarApiError,
    GoogleCalendarConflictError,
    GoogleCalendarError,
    GoogleCalendarInvalidResponseError,
    GoogleCalendarNotFoundError,
    GoogleCalendarResponseDiagnostics,
    GoogleCalendarTransportError,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class _ResponseObservation:
    http_response: Any = None

    def capture(self, response: Any) -> None:
        self.http_response = response


class GoogleCalendarClient:
    """Keep Google discovery/service details outside business contracts."""

    def __init__(self, service: Any) -> None:
        self._service = service

    @classmethod
    def from_credentials_provider(
        cls,
        credential_provider: Callable[[], Any],
        *,
        service_factory: Callable[[Any], Any] | None = None,
    ) -> GoogleCalendarClient:
        credentials = credential_provider()
        factory = service_factory or _default_service_factory
        try:
            return cls(factory(credentials))
        except GoogleCalendarError:
            raise
        except Exception as exc:
            raise GoogleCalendarTransportError() from exc

    def query_freebusy(
        self,
        *,
        calendar_id: str,
        start: datetime,
        end: datetime,
        timezone: str,
    ) -> Mapping[str, Any]:
        body = {
            "timeMin": start.isoformat(),
            "timeMax": end.isoformat(),
            "timeZone": timezone,
            "items": [{"id": calendar_id}],
        }
        request = self._service.freebusy().query(body=body)
        return _execute_request(request, operation="freebusy.query")

    def insert_event(
        self,
        *,
        calendar_id: str,
        event_id: str,
        body: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        request = self._service.events().insert(
            calendarId=calendar_id,
            eventId=event_id,
            body=dict(body),
            sendUpdates="none",
        )
        return _execute_request(
            request,
            operation="events.insert",
            insert=True,
            require_event_resource=True,
        )

    def get_event(
        self,
        *,
        calendar_id: str,
        event_id: str,
    ) -> Mapping[str, Any]:
        request = self._service.events().get(calendarId=calendar_id, eventId=event_id)
        return _execute_request(request, operation="events.get")


def _default_service_factory(credentials: Any) -> Any:
    from googleapiclient.discovery import (  # type: ignore[import-not-found,import-untyped]
        build,
    )

    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def _execute_request(
    request: Any,
    *,
    operation: str,
    insert: bool = False,
    require_event_resource: bool = False,
) -> Mapping[str, Any]:
    observation = _ResponseObservation()
    callbacks = getattr(request, "response_callbacks", None)
    if isinstance(callbacks, list):
        callbacks.append(observation.capture)
    try:
        response = request.execute()
    except Exception as exc:  # noqa: BLE001 - map SDK errors below
        mapped = _map_error(
            exc,
            insert=insert,
            http_response=observation.http_response,
        )
        _log_diagnostics(operation, mapped.diagnostics)
        raise mapped from None
    diagnostics = _diagnostics_for_value(
        response,
        http_response=observation.http_response,
    )
    if require_event_resource:
        return _require_event_resource(response, diagnostics)
    return _require_mapping(response, diagnostics)


def _require_mapping(
    response: Any,
    diagnostics: GoogleCalendarResponseDiagnostics | None = None,
) -> Mapping[str, Any]:
    if not isinstance(response, Mapping):
        raise GoogleCalendarInvalidResponseError(diagnostics=diagnostics)
    return response


def _require_event_resource(
    response: Any,
    diagnostics: GoogleCalendarResponseDiagnostics,
) -> Mapping[str, Any]:
    event = _require_mapping(response, diagnostics)
    event_id = event.get("id")
    if not isinstance(event_id, str) or not event_id.strip():
        raise GoogleCalendarInvalidResponseError(diagnostics=diagnostics)
    return event


def _map_error(
    error: Exception,
    *,
    insert: bool = False,
    http_response: Any = None,
) -> GoogleCalendarError:
    diagnostics = _diagnostics_for_error(error, http_response=http_response)
    status = _http_status(error, response=http_response)
    if status == 404:
        return GoogleCalendarNotFoundError(diagnostics=diagnostics)
    if status == 409:
        return GoogleCalendarConflictError(diagnostics=diagnostics)
    if status is not None:
        return GoogleCalendarApiError(
            status=status,
            ambiguous=insert and (status == 408 or status == 429 or status >= 500),
            diagnostics=diagnostics,
        )
    if isinstance(error, (TimeoutError, OSError)):
        return GoogleCalendarTransportError(diagnostics=diagnostics)
    return GoogleCalendarInvalidResponseError(diagnostics=diagnostics)


def _http_status(error: Exception, *, response: Any = None) -> int | None:
    for candidate in (response, getattr(error, "resp", None)):
        status = getattr(candidate, "status", None)
        if isinstance(status, int) and not isinstance(status, bool):
            return status
        if isinstance(candidate, Mapping):
            status = candidate.get("status")
            if isinstance(status, int) and not isinstance(status, bool):
                return status
    status = getattr(error, "status_code", None)
    if isinstance(status, int) and not isinstance(status, bool):
        return status
    return None


def _diagnostics_for_error(
    error: Exception,
    *,
    http_response: Any = None,
) -> GoogleCalendarResponseDiagnostics:
    response = http_response if http_response is not None else getattr(error, "resp", None)
    content = getattr(error, "content", None)
    decoded, decoded_type = _decode_content_metadata(content)
    return _diagnostics_for_value(
        decoded,
        http_response=response,
        decoded_type=decoded_type,
    )


def _diagnostics_for_value(
    value: Any,
    *,
    http_response: Any = None,
    decoded_type: str | None = None,
) -> GoogleCalendarResponseDiagnostics:
    is_mapping = isinstance(value, Mapping)
    keys = (
        tuple(sorted(str(key) for key in value)) if is_mapping else ()
    )
    return GoogleCalendarResponseDiagnostics(
        http_status=_response_status(http_response),
        content_type=_content_type(http_response),
        decoded_type=(
            decoded_type
            if decoded_type is not None
            else (type(value).__name__ if value is not None else None)
        ),
        top_level_keys=keys,
        has_id=is_mapping and "id" in value,
        has_status=is_mapping and "status" in value,
        has_html_link=is_mapping and "htmlLink" in value,
        has_error=is_mapping and "error" in value,
    )


def _decode_content_metadata(content: Any) -> tuple[Any, str | None]:
    if isinstance(content, bytes):
        try:
            content = content.decode("utf-8")
        except UnicodeDecodeError:
            return None, "bytes"
    if isinstance(content, str):
        try:
            decoded = json.loads(content)
        except json.JSONDecodeError:
            return None, "str"
        return decoded, type(decoded).__name__
    if content is None:
        return None, None
    return None, type(content).__name__


def _response_status(response: Any) -> int | None:
    status = getattr(response, "status", None)
    if isinstance(status, int) and not isinstance(status, bool):
        return status
    if isinstance(response, Mapping):
        status = response.get("status")
        if isinstance(status, int) and not isinstance(status, bool):
            return status
    return None


def _content_type(response: Any) -> str | None:
    value: Any = None
    if isinstance(response, Mapping):
        value = response.get("content-type") or response.get("Content-Type")
    if value is None:
        headers = getattr(response, "headers", None)
        if isinstance(headers, Mapping):
            value = headers.get("content-type") or headers.get("Content-Type")
    return value if isinstance(value, str) else None


def _log_diagnostics(
    operation: str,
    diagnostics: GoogleCalendarResponseDiagnostics | None,
) -> None:
    if diagnostics is not None:
        _LOGGER.warning(
            "google_calendar_response_diagnostics operation=%s diagnostics=%s",
            operation,
            diagnostics.as_dict(),
        )
