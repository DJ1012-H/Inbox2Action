"""Google Calendar read/write adapters for Stage 8."""

from .availability import (
    CalendarAvailability,
    FixtureFreeBusyAdapter,
    GoogleCalendarFreeBusyAdapter,
)
from .client import GoogleCalendarClient
from .diagnostics import (
    InsertAttemptDiagnostic,
    InsertOutcomeClass,
    ReconciliationAttemptDiagnostic,
    ReconciliationDiagnostic,
    ReconciliationOutcome,
)
from .errors import (
    GoogleCalendarApiError,
    GoogleCalendarConfigurationError,
    GoogleCalendarConflictError,
    GoogleCalendarError,
    GoogleCalendarInvalidResponseError,
    GoogleCalendarLocalClientError,
    GoogleCalendarNotFoundError,
    GoogleCalendarResponseDiagnostics,
    GoogleCalendarTransportError,
)
from .executor import GoogleCalendarWriteExecutor
from .runtime import CalendarToolRuntime

__all__ = [
    "CalendarAvailability",
    "CalendarToolRuntime",
    "FixtureFreeBusyAdapter",
    "GoogleCalendarApiError",
    "GoogleCalendarClient",
    "GoogleCalendarConfigurationError",
    "GoogleCalendarConflictError",
    "GoogleCalendarError",
    "GoogleCalendarFreeBusyAdapter",
    "GoogleCalendarInvalidResponseError",
    "GoogleCalendarLocalClientError",
    "GoogleCalendarNotFoundError",
    "GoogleCalendarResponseDiagnostics",
    "GoogleCalendarTransportError",
    "GoogleCalendarWriteExecutor",
    "InsertAttemptDiagnostic",
    "InsertOutcomeClass",
    "ReconciliationAttemptDiagnostic",
    "ReconciliationDiagnostic",
    "ReconciliationOutcome",
]
