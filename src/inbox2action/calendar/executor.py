"""HITL-approved, ledger-guarded Google Calendar event executor."""

from __future__ import annotations

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
from .errors import (
    GoogleCalendarApiError,
    GoogleCalendarConfigurationError,
    GoogleCalendarConflictError,
    GoogleCalendarError,
    GoogleCalendarInvalidResponseError,
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
        reconciliation_attempts: int = 1,
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
        self._sleeper = sleeper

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
            return _succeeded_event(permit, event)
        except GoogleCalendarConflictError:
            return await self.reconcile(permit)
        except GoogleCalendarNotFoundError:
            return _failed("google_calendar_not_found")
        except ValueError:
            return _failed("google_calendar_identity_mismatch")
        except GoogleCalendarApiError as error:
            if error.ambiguous:
                return await self.reconcile(permit)
            return _failed(f"google_calendar_http_{error.status}")
        except (GoogleCalendarTransportError, GoogleCalendarInvalidResponseError):
            return await self.reconcile(permit)
        except GoogleCalendarError as error:
            return _unknown(f"google_calendar_{error.code}")
        except Exception:  # noqa: BLE001 - transport ambiguity blocks replay
            return await self.reconcile(permit)

    async def reconcile(self, permit: ExecutionPermit) -> ExecutionResult:
        if not self._enabled:
            return _unknown("google_calendar_disabled")
        if self._startup_error is not None:
            return _unknown(self._startup_error)
        if self._client is None or self._calendar_id is None:
            return _unknown("google_calendar_configuration")
        if permit.action.tool_name != "save_calendar_proposal":
            return _unknown("google_calendar_unsupported_tool")
        for attempt in range(self._reconciliation_attempts):
            if attempt and self._sleeper is not None:
                await self._sleeper(float(attempt))
            try:
                event = self._client.get_event(
                    calendar_id=self._calendar_id,
                    event_id=permit.idempotency_key,
                )
            except GoogleCalendarNotFoundError:
                return _unknown("google_calendar_reconciliation_unresolved")
            except GoogleCalendarError:
                if attempt + 1 < self._reconciliation_attempts:
                    continue
                return _unknown("google_calendar_reconciliation_failed")
            except Exception:  # noqa: BLE001 - GET recovery remains fail-closed
                if attempt + 1 < self._reconciliation_attempts:
                    continue
                return _unknown("google_calendar_reconciliation_failed")
            try:
                return _succeeded_event(permit, event)
            except ValueError:
                return _failed("google_calendar_identity_mismatch")
        return _unknown("google_calendar_reconciliation_unresolved")


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


def _failed(error_code: str) -> ExecutionResult:
    return ExecutionResult(status="failed", error_code=error_code)


def _unknown(error_code: str) -> ExecutionResult:
    return ExecutionResult(status="unknown", error_code=error_code)
