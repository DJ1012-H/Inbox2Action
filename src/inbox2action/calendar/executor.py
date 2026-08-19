"""HITL-approved, ledger-guarded Google Calendar event executor."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import TYPE_CHECKING, Protocol

from inbox2action.gmail import (
    DEFAULT_CLIENT_SECRETS_PATH,
    DEFAULT_TOKEN_PATH,
    GmailOAuthConfig,
    GoogleOAuthCredentialProvider,
)
from inbox2action.stage3.contracts import (
    ExecutionPermit,
    ExecutionResult,
    ExternalResourceRef,
)
from inbox2action.tools.schemas import SaveCalendarProposalArgs

from .client import GoogleCalendarClient
from .diagnostics import (
    InsertAttemptDiagnostic,
    InsertOutcomeClass,
    ReconciliationAttemptDiagnostic,
    ReconciliationDiagnostic,
    ReconciliationOutcome,
    diagnostic_bundle,
    sanitized_text,
)
from .errors import (
    GoogleCalendarApiError,
    GoogleCalendarConfigurationError,
    GoogleCalendarConflictError,
    GoogleCalendarError,
    GoogleCalendarInvalidResponseError,
    GoogleCalendarLocalClientError,
    GoogleCalendarNotFoundError,
    GoogleCalendarTransportError,
)

if TYPE_CHECKING:
    from inbox2action.config import Settings


class CalendarEventClient(Protocol):
    def insert_event(
        self,
        *,
        calendar_id: str,
        event_id: str,
        body: Mapping[str, object],
    ) -> Mapping[str, object]: ...

    def get_event(
        self,
        *,
        calendar_id: str,
        event_id: str,
    ) -> Mapping[str, object]: ...


class GoogleCalendarWriteExecutor:
    """Translate one approved proposal into one deterministic Events.insert."""

    def __init__(
        self,
        client: CalendarEventClient | None = None,
        *,
        calendar_id: str | None = None,
        timezone: str = "Asia/Shanghai",
        enabled: bool = False,
        startup_error: str | None = None,
        reconciliation_attempts: int = 3,
        sleeper: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        if not 1 <= reconciliation_attempts <= 3:
            raise ValueError("reconciliation_attempts must be between 1 and 3")
        self._client = client
        self._calendar_id = calendar_id
        self._timezone = timezone
        self._enabled = enabled
        self._startup_error = startup_error
        self._reconciliation_attempts = reconciliation_attempts
        self._sleeper = sleeper or asyncio.sleep

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        credential_provider: GoogleOAuthCredentialProvider | None = None,
    ) -> GoogleCalendarWriteExecutor:
        if not settings.google_calendar_enabled:
            return cls(enabled=False, timezone=settings.business_timezone)
        if settings.google_calendar_id is None:
            return cls(
                enabled=True,
                timezone=settings.business_timezone,
                startup_error="google_calendar_configuration",
            )
        provider = credential_provider or GoogleOAuthCredentialProvider(
            GmailOAuthConfig(
                client_secrets_path=(
                    settings.gmail_client_secrets_path or DEFAULT_CLIENT_SECRETS_PATH
                ),
                token_path=settings.gmail_token_path or DEFAULT_TOKEN_PATH,
            )
        )
        try:
            client = GoogleCalendarClient.from_credentials_provider(provider)
        except Exception:  # noqa: BLE001 - startup remains fail-closed and safe
            return cls(
                enabled=True,
                calendar_id=settings.google_calendar_id,
                timezone=settings.business_timezone,
                startup_error="google_calendar_credentials",
            )
        return cls(
            client,
            calendar_id=settings.google_calendar_id,
            timezone=settings.business_timezone,
            enabled=True,
        )

    async def execute(self, permit: ExecutionPermit) -> ExecutionResult:
        if not self._enabled:
            return _failed("google_calendar_disabled")
        if self._startup_error is not None:
            return _failed(self._startup_error)
        if self._client is None or self._calendar_id is None:
            return _failed("google_calendar_configuration")
        if permit.action.tool_name != "save_calendar_proposal":
            return _failed("google_calendar_unsupported_tool")
        try:
            proposal = SaveCalendarProposalArgs.model_validate(permit.action.parameters)
            if proposal.timezone != self._timezone:
                raise GoogleCalendarConfigurationError("trusted_timezone_mismatch")
            body = build_event_body(permit, proposal)
        except GoogleCalendarError as error:
            return _failed(f"google_calendar_{error.code}")
        except ValueError:
            return _failed("google_calendar_invalid_request")

        try:
            event = self._client.insert_event(
                calendar_id=self._calendar_id,
                event_id=permit.idempotency_key,
                body=body,
            )
            insert_diagnostic = _client_insert_diagnostic(self._client)
            return _succeeded_event(permit, event, insert_diagnostic)
        except GoogleCalendarConflictError as error:
            return await self.reconcile(
                permit,
                insert_diagnostic=_error_insert_diagnostic(
                    error,
                    fallback_class=InsertOutcomeClass.DUPLICATE_409,
                ),
            )
        except GoogleCalendarNotFoundError as error:
            return _failed(
                "google_calendar_not_found",
                _diagnostic_bundle_for_error(error),
            )
        except ValueError:
            return _failed(
                "google_calendar_identity_mismatch",
                diagnostic_bundle(
                    _client_insert_diagnostic(self._client),
                    None,
                ),
            )
        except GoogleCalendarApiError as error:
            return _failed(
                f"google_calendar_http_{error.status}",
                _diagnostic_bundle_for_error(error),
            )
        except GoogleCalendarTransportError as error:
            return await self.reconcile(
                permit,
                insert_diagnostic=_error_insert_diagnostic(
                    error,
                    fallback_class=InsertOutcomeClass.AMBIGUOUS_TRANSPORT_FAILURE,
                ),
            )
        except GoogleCalendarInvalidResponseError as error:
            insert_diagnostic = _error_insert_diagnostic(
                error,
                fallback_class=InsertOutcomeClass.INVALID_SUCCESS_RESPONSE,
            )
            return await self.reconcile(
                permit,
                insert_diagnostic=insert_diagnostic,
            )
        except GoogleCalendarLocalClientError as error:
            return _failed(
                "google_calendar_local_client_failure",
                _diagnostic_bundle_for_error(error),
            )
        except GoogleCalendarError as error:
            return _unknown(
                f"google_calendar_{error.code}",
                _diagnostic_bundle_for_error(error),
            )
        except Exception as error:  # noqa: BLE001 - preserve unknown local failures
            return _failed(
                "google_calendar_local_client_failure",
                diagnostic_bundle(_fallback_insert_diagnostic(error), None),
            )

    async def reconcile(
        self,
        permit: ExecutionPermit,
        *,
        insert_diagnostic: InsertAttemptDiagnostic | None = None,
    ) -> ExecutionResult:
        if not self._enabled:
            return _unknown("google_calendar_disabled")
        if self._startup_error is not None:
            return _unknown(self._startup_error)
        if self._client is None or self._calendar_id is None:
            return _unknown("google_calendar_configuration")
        if permit.action.tool_name != "save_calendar_proposal":
            return _unknown("google_calendar_unsupported_tool")
        attempts: list[ReconciliationAttemptDiagnostic] = []
        for attempt in range(self._reconciliation_attempts):
            if attempt:
                await self._sleeper(float(2 ** (attempt - 1)))
            try:
                event = self._client.get_event(
                    calendar_id=self._calendar_id,
                    event_id=permit.idempotency_key,
                )
            except GoogleCalendarNotFoundError as error:
                attempts.append(
                    _reconciliation_attempt(
                        self._client,
                        attempt=attempt + 1,
                        outcome=ReconciliationOutcome.NOT_FOUND,
                        error=error,
                    )
                )
                continue
            except GoogleCalendarError as error:
                attempts.append(
                    _reconciliation_attempt(
                        self._client,
                        attempt=attempt + 1,
                        outcome=ReconciliationOutcome.FAILED,
                        error=error,
                    )
                )
                if attempt + 1 < self._reconciliation_attempts:
                    continue
                return _unknown(
                    "google_calendar_reconciliation_failed",
                    _diagnostic_bundle(
                        insert_diagnostic,
                        attempts,
                        ReconciliationOutcome.FAILED,
                    ),
                )
            except Exception as error:  # noqa: BLE001 - GET recovery remains fail-closed
                attempts.append(
                    _reconciliation_attempt(
                        self._client,
                        attempt=attempt + 1,
                        outcome=ReconciliationOutcome.FAILED,
                        error=error,
                    )
                )
                if attempt + 1 < self._reconciliation_attempts:
                    continue
                return _unknown(
                    "google_calendar_reconciliation_failed",
                    _diagnostic_bundle(
                        insert_diagnostic,
                        attempts,
                        ReconciliationOutcome.FAILED,
                    ),
                )
            try:
                identity_matches = _identity_matches(event, permit)
                attempts.append(
                    _reconciliation_attempt(
                        self._client,
                        attempt=attempt + 1,
                        outcome=(
                            ReconciliationOutcome.FOUND_IDENTITY_MATCH
                            if identity_matches
                            else ReconciliationOutcome.FOUND_IDENTITY_MISMATCH
                        ),
                        found=True,
                        identity_match=identity_matches,
                    )
                )
                if not identity_matches:
                    return _failed(
                        "google_calendar_identity_mismatch",
                        _diagnostic_bundle(
                            insert_diagnostic,
                            attempts,
                            ReconciliationOutcome.FOUND_IDENTITY_MISMATCH,
                        ),
                    )
                return _succeeded_event(
                    permit,
                    event,
                    insert_diagnostic,
                    _reconciliation_diagnostic(
                        attempts,
                        ReconciliationOutcome.FOUND_IDENTITY_MATCH,
                    ),
                )
            except ValueError:
                return _failed(
                    "google_calendar_identity_mismatch",
                    _diagnostic_bundle(
                        insert_diagnostic,
                        attempts,
                        ReconciliationOutcome.FOUND_IDENTITY_MISMATCH,
                    ),
                )
        return _unknown(
            "google_calendar_reconciliation_unresolved",
            _diagnostic_bundle(
                insert_diagnostic,
                attempts,
                ReconciliationOutcome.NOT_FOUND,
            ),
        )


def build_event_body(
    permit: ExecutionPermit,
    proposal: SaveCalendarProposalArgs,
) -> dict[str, object]:
    private_identity = {
        "i2a_k": permit.idempotency_key,
        "i2a_h": permit.approved_payload_hash,
        "i2a_a": permit.action_id,
    }
    body: dict[str, object] = {
        "id": permit.idempotency_key,
        "summary": proposal.summary,
        "start": {
            "dateTime": proposal.start_time.isoformat(),
            "timeZone": proposal.timezone,
        },
        "end": {
            "dateTime": proposal.end_time.isoformat(),
            "timeZone": proposal.timezone,
        },
        "extendedProperties": {"private": private_identity},
    }
    if proposal.description is not None:
        body["description"] = proposal.description
    if proposal.location is not None:
        body["location"] = proposal.location
    return body


def _succeeded_event(
    permit: ExecutionPermit,
    event: Mapping[str, object],
    insert_diagnostic: InsertAttemptDiagnostic | None = None,
    reconciliation: ReconciliationDiagnostic | None = None,
) -> ExecutionResult:
    event_id = event.get("id")
    if (
        not isinstance(event_id, str)
        or event_id != permit.idempotency_key
        or not _identity_matches(event, permit)
    ):
        raise ValueError("event identity does not match approved operation")
    url = event.get("htmlLink")
    safe_url = url if isinstance(url, str) and url.startswith("https://") else None
    return ExecutionResult(
        status="succeeded",
        resource=ExternalResourceRef(
            provider="google_calendar",
            resource_type="event",
            resource_id=event_id,
            url=safe_url,
        ),
        diagnostics=diagnostic_bundle(insert_diagnostic, reconciliation),
    )


def _identity_matches(event: Mapping[str, object], permit: ExecutionPermit) -> bool:
    extended = event.get("extendedProperties")
    if not isinstance(extended, Mapping):
        return False
    private = extended.get("private")
    if not isinstance(private, Mapping):
        return False
    return (
        private.get("i2a_k") == permit.idempotency_key
        and private.get("i2a_h") == permit.approved_payload_hash
        and private.get("i2a_a") == permit.action_id
    )


def _failed(
    error_code: str,
    diagnostics: dict[str, object] | None = None,
) -> ExecutionResult:
    return ExecutionResult(
        status="failed",
        error_code=error_code,
        diagnostics=diagnostics,
    )


def _unknown(
    error_code: str,
    diagnostics: dict[str, object] | None = None,
) -> ExecutionResult:
    return ExecutionResult(
        status="unknown",
        error_code=error_code,
        diagnostics=diagnostics,
    )


def _client_insert_diagnostic(
    client: CalendarEventClient,
) -> InsertAttemptDiagnostic | None:
    diagnostic = getattr(client, "last_insert_diagnostic", None)
    return diagnostic if isinstance(diagnostic, InsertAttemptDiagnostic) else None


def _error_insert_diagnostic(
    error: GoogleCalendarError,
    *,
    fallback_class: InsertOutcomeClass,
) -> InsertAttemptDiagnostic:
    if error.insert_diagnostic is not None:
        return error.insert_diagnostic
    return InsertAttemptDiagnostic(
        outcome_class=fallback_class,
        exception_type=type(error).__name__,
        http_status=error.status,
        provider_reason=sanitized_text(error),
        response_received=error.status is not None,
        request_may_have_reached_server=True,
    )


def _fallback_insert_diagnostic(error: Exception) -> InsertAttemptDiagnostic:
    return InsertAttemptDiagnostic(
        outcome_class=InsertOutcomeClass.LOCAL_CLIENT_FAILURE,
        exception_type=type(error).__name__,
        provider_reason=sanitized_text(error),
        request_may_have_reached_server=True,
    )


def _diagnostic_bundle_for_error(
    error: GoogleCalendarError,
) -> dict[str, object]:
    return diagnostic_bundle(error.insert_diagnostic, None)


def _reconciliation_attempt(
    client: CalendarEventClient,
    *,
    attempt: int,
    outcome: ReconciliationOutcome,
    error: Exception | None = None,
    found: bool = False,
    identity_match: bool | None = None,
) -> ReconciliationAttemptDiagnostic:
    response_diagnostic = getattr(client, "last_get_diagnostic", None)
    status = (
        response_diagnostic.http_status
        if response_diagnostic is not None
        else getattr(error, "status", None)
    )
    provider_reason = None
    if isinstance(error, GoogleCalendarError) and error.insert_diagnostic is not None:
        provider_reason = error.insert_diagnostic.provider_reason
    return ReconciliationAttemptDiagnostic(
        attempt=attempt,
        http_status=status,
        outcome=outcome,
        found=found,
        identity_match=identity_match,
        exception_type=type(error).__name__ if error is not None else None,
        provider_reason=provider_reason,
    )


def _reconciliation_diagnostic(
    attempts: list[ReconciliationAttemptDiagnostic],
    final_outcome: ReconciliationOutcome,
) -> ReconciliationDiagnostic:
    return ReconciliationDiagnostic(
        get_attempt_count=len(attempts),
        attempts=tuple(attempts),
        final_outcome=final_outcome,
    )


def _diagnostic_bundle(
    insert_diagnostic: InsertAttemptDiagnostic | None,
    attempts: list[ReconciliationAttemptDiagnostic],
    final_outcome: ReconciliationOutcome,
) -> dict[str, object]:
    return diagnostic_bundle(
        insert_diagnostic,
        _reconciliation_diagnostic(attempts, final_outcome),
    )
