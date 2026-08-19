"""Safe error taxonomy for the Google Calendar boundary."""

from __future__ import annotations


class GoogleCalendarError(Exception):
    """Base error whose message is a non-secret stable code."""

    code = "google_calendar_error"

    def __init__(self, code: str | None = None, *, status: int | None = None) -> None:
        self.code = code or self.code
        self.status = status
        super().__init__(self.code)


class GoogleCalendarConfigurationError(GoogleCalendarError):
    code = "configuration"


class GoogleCalendarInvalidResponseError(GoogleCalendarError):
    code = "invalid_response"


class GoogleCalendarTransportError(GoogleCalendarError):
    code = "transport_ambiguous"


class GoogleCalendarApiError(GoogleCalendarError):
    code = "api_error"

    def __init__(self, *, status: int, ambiguous: bool = False) -> None:
        super().__init__(status=status)
        self.ambiguous = ambiguous


class GoogleCalendarConflictError(GoogleCalendarApiError):
    code = "duplicate_event"

    def __init__(self) -> None:
        super().__init__(status=409, ambiguous=True)


class GoogleCalendarNotFoundError(GoogleCalendarApiError):
    code = "not_found"

    def __init__(self) -> None:
        super().__init__(status=404, ambiguous=False)
