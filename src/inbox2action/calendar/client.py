"""Small injectable Google Calendar API client."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from .errors import (
    GoogleCalendarApiError,
    GoogleCalendarConflictError,
    GoogleCalendarError,
    GoogleCalendarInvalidResponseError,
    GoogleCalendarNotFoundError,
    GoogleCalendarTransportError,
)


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
        try:
            response = (
                self._service.freebusy()
                .query(body=body)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001 - map SDK errors below
            raise _map_error(exc) from None
        return _require_mapping(response)

    def insert_event(
        self,
        *,
        calendar_id: str,
        event_id: str,
        body: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        try:
            response = (
                self._service.events()
                .insert(
                    calendarId=calendar_id,
                    eventId=event_id,
                    body=dict(body),
                    sendUpdates="none",
                )
                .execute()
            )
        except Exception as exc:  # noqa: BLE001 - map SDK errors below
            raise _map_error(exc, insert=True) from None
        return _require_mapping(response)

    def get_event(
        self,
        *,
        calendar_id: str,
        event_id: str,
    ) -> Mapping[str, Any]:
        try:
            response = (
                self._service.events()
                .get(calendarId=calendar_id, eventId=event_id)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001 - map SDK errors below
            raise _map_error(exc) from None
        return _require_mapping(response)


def _default_service_factory(credentials: Any) -> Any:
    from googleapiclient.discovery import build  # type: ignore[import-not-found]

    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def _require_mapping(response: Any) -> Mapping[str, Any]:
    if not isinstance(response, Mapping):
        raise GoogleCalendarInvalidResponseError()
    return response


def _map_error(error: Exception, *, insert: bool = False) -> GoogleCalendarError:
    status = _http_status(error)
    if status == 404:
        return GoogleCalendarNotFoundError()
    if status == 409:
        return GoogleCalendarConflictError()
    if status is not None:
        return GoogleCalendarApiError(
            status=status,
            ambiguous=insert and (status == 408 or status == 429 or status >= 500),
        )
    if isinstance(error, (TimeoutError, OSError)):
        return GoogleCalendarTransportError()
    return GoogleCalendarInvalidResponseError()


def _http_status(error: Exception) -> int | None:
    response = getattr(error, "resp", None)
    status = getattr(response, "status", None)
    if isinstance(status, int) and not isinstance(status, bool):
        return status
    status = getattr(error, "status_code", None)
    if isinstance(status, int) and not isinstance(status, bool):
        return status
    return None
