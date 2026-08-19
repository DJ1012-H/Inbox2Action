"""Safe error taxonomy for the Google Calendar boundary."""

from __future__ import annotations

from dataclasses import dataclass

from .diagnostics import InsertAttemptDiagnostic


@dataclass(frozen=True, slots=True)
class GoogleCalendarResponseDiagnostics:
    """Secret-free metadata captured at the Google API response boundary."""

    http_status: int | None = None
    content_type: str | None = None
    decoded_type: str | None = None
    top_level_keys: tuple[str, ...] = ()
    has_id: bool = False
    has_status: bool = False
    has_html_link: bool = False
    has_error: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "http_status": self.http_status,
            "content_type": self.content_type,
            "decoded_type": self.decoded_type,
            "top_level_keys": self.top_level_keys,
            "has_id": self.has_id,
            "has_status": self.has_status,
            "has_htmlLink": self.has_html_link,
            "has_error": self.has_error,
        }


class GoogleCalendarError(Exception):
    """Base error whose message is a non-secret stable code."""

    code = "google_calendar_error"

    def __init__(
        self,
        code: str | None = None,
        *,
        status: int | None = None,
        diagnostics: GoogleCalendarResponseDiagnostics | None = None,
        insert_diagnostic: InsertAttemptDiagnostic | None = None,
    ) -> None:
        self.code = code or self.code
        self.status = status
        self.diagnostics = diagnostics
        self.insert_diagnostic = insert_diagnostic
        super().__init__(self.code)


class GoogleCalendarConfigurationError(GoogleCalendarError):
    code = "configuration"


class GoogleCalendarInvalidResponseError(GoogleCalendarError):
    code = "invalid_response"


class GoogleCalendarLocalClientError(GoogleCalendarError):
    code = "local_client_failure"


class GoogleCalendarTransportError(GoogleCalendarError):
    code = "transport_ambiguous"


class GoogleCalendarApiError(GoogleCalendarError):
    code = "api_error"

    def __init__(
        self,
        *,
        status: int,
        ambiguous: bool = False,
        diagnostics: GoogleCalendarResponseDiagnostics | None = None,
        insert_diagnostic: InsertAttemptDiagnostic | None = None,
    ) -> None:
        super().__init__(
            status=status,
            diagnostics=diagnostics,
            insert_diagnostic=insert_diagnostic,
        )
        self.ambiguous = ambiguous


class GoogleCalendarConflictError(GoogleCalendarApiError):
    code = "duplicate_event"

    def __init__(
        self,
        *,
        diagnostics: GoogleCalendarResponseDiagnostics | None = None,
        insert_diagnostic: InsertAttemptDiagnostic | None = None,
    ) -> None:
        super().__init__(
            status=409,
            ambiguous=True,
            diagnostics=diagnostics,
            insert_diagnostic=insert_diagnostic,
        )


class GoogleCalendarNotFoundError(GoogleCalendarApiError):
    code = "not_found"

    def __init__(
        self,
        *,
        diagnostics: GoogleCalendarResponseDiagnostics | None = None,
        insert_diagnostic: InsertAttemptDiagnostic | None = None,
    ) -> None:
        super().__init__(
            status=404,
            ambiguous=False,
            diagnostics=diagnostics,
            insert_diagnostic=insert_diagnostic,
        )
