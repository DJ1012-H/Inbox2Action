"""Small injectable Google Calendar API client."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .diagnostics import (
    InsertAttemptDiagnostic,
    InsertOutcomeClass,
    sanitized_text,
)
from .errors import (
    GoogleCalendarApiError,
    GoogleCalendarConflictError,
    GoogleCalendarError,
    GoogleCalendarInvalidResponseError,
    GoogleCalendarLocalClientError,
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
        self.last_insert_diagnostic: InsertAttemptDiagnostic | None = None
        self.last_get_diagnostic: GoogleCalendarResponseDiagnostics | None = None

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
        self.last_insert_diagnostic = None
        try:
            request = self._service.events().insert(
                calendarId=calendar_id,
                eventId=event_id,
                body=dict(body),
                sendUpdates="none",
            )
        except Exception as exc:  # noqa: BLE001 - local request construction boundary
            diagnostic = _local_insert_diagnostic(exc)
            self.last_insert_diagnostic = diagnostic
            raise GoogleCalendarLocalClientError(
                insert_diagnostic=diagnostic
            ) from None
        return _execute_request(
            request,
            operation="events.insert",
            insert=True,
            require_event_resource=True,
            insert_diagnostic_sink=self._record_insert_diagnostic,
        )

    def get_event(
        self,
        *,
        calendar_id: str,
        event_id: str,
    ) -> Mapping[str, Any]:
        self.last_get_diagnostic = None
        try:
            request = self._service.events().get(
                calendarId=calendar_id,
                eventId=event_id,
            )
        except Exception:  # noqa: BLE001 - local request construction boundary
            raise GoogleCalendarLocalClientError() from None
        return _execute_request(
            request,
            operation="events.get",
            response_diagnostic_sink=self._record_get_diagnostic,
        )

    def _record_insert_diagnostic(self, diagnostic: InsertAttemptDiagnostic) -> None:
        self.last_insert_diagnostic = diagnostic

    def _record_get_diagnostic(
        self,
        diagnostic: GoogleCalendarResponseDiagnostics,
    ) -> None:
        self.last_get_diagnostic = diagnostic


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
    insert_diagnostic_sink: Callable[[InsertAttemptDiagnostic], None] | None = None,
    response_diagnostic_sink: Callable[
        [GoogleCalendarResponseDiagnostics], None
    ] | None = None,
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
            request_may_have_reached_server=True,
        )
        if mapped.diagnostics is not None and response_diagnostic_sink is not None:
            response_diagnostic_sink(mapped.diagnostics)
        if mapped.insert_diagnostic is not None and insert_diagnostic_sink is not None:
            insert_diagnostic_sink(mapped.insert_diagnostic)
        _log_diagnostics(operation, mapped.diagnostics)
        _log_insert_diagnostic(operation, mapped.insert_diagnostic)
        raise mapped from None
    diagnostics = _diagnostics_for_value(
        response,
        http_response=observation.http_response,
    )
    if response_diagnostic_sink is not None:
        response_diagnostic_sink(diagnostics)
    if require_event_resource:
        try:
            event = _require_event_resource(response, diagnostics)
        except GoogleCalendarInvalidResponseError as error:
            diagnostic = _insert_response_diagnostic(
                diagnostics,
                outcome_class=InsertOutcomeClass.INVALID_SUCCESS_RESPONSE,
            )
            if insert_diagnostic_sink is not None:
                insert_diagnostic_sink(diagnostic)
            raise GoogleCalendarInvalidResponseError(
                diagnostics=diagnostics,
                insert_diagnostic=diagnostic,
            ) from error
        diagnostic = _insert_response_diagnostic(
            diagnostics,
            outcome_class=InsertOutcomeClass.SUCCESS_RESPONSE,
        )
        if insert_diagnostic_sink is not None:
            insert_diagnostic_sink(diagnostic)
        return event
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
    request_may_have_reached_server: bool = True,
) -> GoogleCalendarError:
    diagnostics, decoded = _diagnostics_for_error(
        error,
        http_response=http_response,
    )
    status = _http_status(error, response=http_response)
    insert_diagnostic = None
    if insert:
        if status == 409:
            outcome_class = InsertOutcomeClass.DUPLICATE_409
        elif status is not None and status < 300:
            outcome_class = InsertOutcomeClass.INVALID_SUCCESS_RESPONSE
        elif status is not None:
            outcome_class = InsertOutcomeClass.DEFINITIVE_HTTP_FAILURE
        elif isinstance(error, (TimeoutError, OSError)):
            outcome_class = InsertOutcomeClass.AMBIGUOUS_TRANSPORT_FAILURE
        else:
            outcome_class = InsertOutcomeClass.LOCAL_CLIENT_FAILURE
        insert_diagnostic = _insert_error_diagnostic(
            error,
            diagnostics=diagnostics,
            decoded=decoded,
            outcome_class=outcome_class,
            request_may_have_reached_server=request_may_have_reached_server,
        )
    if status == 404:
        return GoogleCalendarNotFoundError(
            diagnostics=diagnostics,
            insert_diagnostic=insert_diagnostic,
        )
    if status == 409:
        return GoogleCalendarConflictError(
            diagnostics=diagnostics,
            insert_diagnostic=insert_diagnostic,
        )
    if status is not None:
        return GoogleCalendarApiError(
            status=status,
            ambiguous=False,
            diagnostics=diagnostics,
            insert_diagnostic=insert_diagnostic,
        )
    if isinstance(error, (TimeoutError, OSError)):
        return GoogleCalendarTransportError(
            diagnostics=diagnostics,
            insert_diagnostic=insert_diagnostic,
        )
    return GoogleCalendarLocalClientError(
        diagnostics=diagnostics,
        insert_diagnostic=insert_diagnostic,
    )


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
) -> tuple[GoogleCalendarResponseDiagnostics, Any]:
    response = http_response if http_response is not None else getattr(error, "resp", None)
    content = getattr(error, "content", None)
    decoded, decoded_type = _decode_content_metadata(content)
    return _diagnostics_for_value(
        decoded,
        http_response=response,
        decoded_type=decoded_type,
    ), decoded


def _insert_response_diagnostic(
    diagnostics: GoogleCalendarResponseDiagnostics,
    *,
    outcome_class: InsertOutcomeClass,
) -> InsertAttemptDiagnostic:
    return InsertAttemptDiagnostic(
        outcome_class=outcome_class,
        http_status=diagnostics.http_status,
        content_type=diagnostics.content_type,
        decoded_type=diagnostics.decoded_type,
        top_level_keys=diagnostics.top_level_keys,
        has_id=diagnostics.has_id,
        has_status=diagnostics.has_status,
        has_html_link=diagnostics.has_html_link,
        has_error=diagnostics.has_error,
        response_received=True,
        request_may_have_reached_server=True,
    )


def _insert_error_diagnostic(
    error: Exception,
    *,
    diagnostics: GoogleCalendarResponseDiagnostics,
    decoded: Any,
    outcome_class: InsertOutcomeClass,
    request_may_have_reached_server: bool,
) -> InsertAttemptDiagnostic:
    return InsertAttemptDiagnostic(
        outcome_class=outcome_class,
        exception_type=type(error).__name__,
        http_status=diagnostics.http_status,
        content_type=diagnostics.content_type,
        decoded_type=diagnostics.decoded_type,
        top_level_keys=diagnostics.top_level_keys,
        has_id=diagnostics.has_id,
        has_status=diagnostics.has_status,
        has_html_link=diagnostics.has_html_link,
        has_error=diagnostics.has_error,
        provider_reason=_provider_reason(error, decoded),
        response_received=diagnostics.http_status is not None
        or diagnostics.content_type is not None
        or diagnostics.has_error,
        request_may_have_reached_server=request_may_have_reached_server,
    )


def _local_insert_diagnostic(error: Exception) -> InsertAttemptDiagnostic:
    return InsertAttemptDiagnostic(
        outcome_class=InsertOutcomeClass.LOCAL_CLIENT_FAILURE,
        exception_type=type(error).__name__,
        provider_reason=sanitized_text(error),
        response_received=False,
        request_may_have_reached_server=False,
    )


def _provider_reason(error: Exception, decoded: Any) -> str | None:
    if isinstance(decoded, Mapping):
        payload = decoded.get("error")
        if isinstance(payload, Mapping):
            reason: str | None = None
            errors = payload.get("errors")
            if isinstance(errors, list) and errors:
                first = errors[0]
                if isinstance(first, Mapping) and isinstance(first.get("reason"), str):
                    reason = first["reason"]
            message = payload.get("message")
            if reason and isinstance(message, str):
                return sanitized_text(f"{reason}: {message}")
            if isinstance(message, str):
                return sanitized_text(message)
            if reason:
                return sanitized_text(reason)
    return sanitized_text(getattr(error, "reason", None) or error)


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


def _log_insert_diagnostic(
    operation: str,
    diagnostic: InsertAttemptDiagnostic | None,
) -> None:
    if diagnostic is not None:
        _LOGGER.warning(
            "google_calendar_insert_diagnostic operation=%s diagnostic=%s",
            operation,
            diagnostic.as_dict(),
        )
