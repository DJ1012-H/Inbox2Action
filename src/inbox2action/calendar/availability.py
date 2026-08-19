"""Trusted-timezone FreeBusy adapters with fail-closed parsing."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .client import GoogleCalendarClient
from .errors import (
    GoogleCalendarConfigurationError,
    GoogleCalendarInvalidResponseError,
)


@dataclass(frozen=True)
class CalendarBusyInterval:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class CalendarAvailability:
    available: bool
    timezone: str
    busy_intervals: tuple[CalendarBusyInterval, ...] = ()
    error_code: str | None = None


class FreeBusyAdapter(Protocol):
    def check(
        self,
        *,
        start: datetime,
        end: datetime,
        timezone: str,
    ) -> CalendarAvailability:
        """Return FREE/BUSY/ERROR without treating provider errors as FREE."""


class GoogleCalendarFreeBusyAdapter:
    """Production FreeBusy adapter bound to one trusted Calendar ID and zone."""

    def __init__(
        self,
        client: GoogleCalendarClient,
        *,
        calendar_id: str,
        timezone: str = "Asia/Shanghai",
    ) -> None:
        _validate_timezone(timezone)
        if not calendar_id.strip():
            raise GoogleCalendarConfigurationError()
        self._client = client
        self.calendar_id = calendar_id
        self.timezone = timezone

    def check(
        self,
        *,
        start: datetime,
        end: datetime,
        timezone: str,
    ) -> CalendarAvailability:
        _validate_interval(start, end)
        if timezone != self.timezone:
            raise GoogleCalendarConfigurationError("trusted_timezone_mismatch")
        zone = _validate_timezone(self.timezone)
        normalized_start = start.astimezone(zone)
        normalized_end = end.astimezone(zone)
        response = self._client.query_freebusy(
            calendar_id=self.calendar_id,
            start=normalized_start,
            end=normalized_end,
            timezone=self.timezone,
        )
        busy = _parse_busy_response(response, self.calendar_id, zone)
        return CalendarAvailability(
            available=not bool(busy),
            timezone=self.timezone,
            busy_intervals=tuple(busy),
        )


@dataclass
class FixtureFreeBusyAdapter:
    """Offline adapter; it never constructs or calls a Google client."""

    busy_intervals: Sequence[tuple[datetime, datetime]] = ()
    provider_error: str | None = None
    call_count: int = 0
    calls: list[tuple[datetime, datetime, str]] = field(default_factory=list)

    def check(
        self,
        *,
        start: datetime,
        end: datetime,
        timezone: str,
    ) -> CalendarAvailability:
        _validate_interval(start, end)
        self.call_count += 1
        self.calls.append((start, end, timezone))
        if self.provider_error is not None:
            return CalendarAvailability(
                available=False,
                timezone=timezone,
                error_code=self.provider_error,
            )
        busy = tuple(
            CalendarBusyInterval(busy_start, busy_end)
            for busy_start, busy_end in self.busy_intervals
            if start < busy_end and end > busy_start
        )
        return CalendarAvailability(
            available=not bool(busy),
            timezone=timezone,
            busy_intervals=busy,
        )


def _parse_busy_response(
    response: Mapping[str, object],
    calendar_id: str,
    timezone: ZoneInfo,
) -> list[CalendarBusyInterval]:
    calendars = response.get("calendars")
    if not isinstance(calendars, Mapping):
        raise GoogleCalendarInvalidResponseError()
    calendar = calendars.get(calendar_id)
    if not isinstance(calendar, Mapping):
        raise GoogleCalendarInvalidResponseError()
    if calendar.get("errors") not in (None, []):
        raise GoogleCalendarInvalidResponseError()
    busy_values = calendar.get("busy")
    if not isinstance(busy_values, list):
        raise GoogleCalendarInvalidResponseError()
    intervals: list[CalendarBusyInterval] = []
    for item in busy_values:
        if not isinstance(item, Mapping):
            raise GoogleCalendarInvalidResponseError()
        start = _parse_aware_datetime(item.get("start"), timezone)
        end = _parse_aware_datetime(item.get("end"), timezone)
        if end <= start:
            raise GoogleCalendarInvalidResponseError()
        intervals.append(CalendarBusyInterval(start, end))
    return intervals


def _parse_aware_datetime(value: object, timezone: ZoneInfo) -> datetime:
    if not isinstance(value, str):
        raise GoogleCalendarInvalidResponseError()
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise GoogleCalendarInvalidResponseError() from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise GoogleCalendarInvalidResponseError()
    return parsed.astimezone(timezone)


def _validate_timezone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise GoogleCalendarConfigurationError() from exc


def _validate_interval(start: datetime, end: datetime) -> None:
    if start.tzinfo is None or start.utcoffset() is None:
        raise GoogleCalendarConfigurationError("naive_datetime")
    if end.tzinfo is None or end.utcoffset() is None:
        raise GoogleCalendarConfigurationError("naive_datetime")
    if end <= start:
        raise GoogleCalendarConfigurationError("invalid_interval")
