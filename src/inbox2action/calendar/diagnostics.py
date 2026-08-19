"""Secret-free provider and reconciliation diagnostics for Calendar writes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class InsertOutcomeClass(StrEnum):
    SUCCESS_RESPONSE = "SUCCESS_RESPONSE"
    DEFINITIVE_HTTP_FAILURE = "DEFINITIVE_HTTP_FAILURE"
    DUPLICATE_409 = "DUPLICATE_409"
    AMBIGUOUS_TRANSPORT_FAILURE = "AMBIGUOUS_TRANSPORT_FAILURE"
    INVALID_SUCCESS_RESPONSE = "INVALID_SUCCESS_RESPONSE"
    LOCAL_CLIENT_FAILURE = "LOCAL_CLIENT_FAILURE"


class ReconciliationOutcome(StrEnum):
    FOUND_IDENTITY_MATCH = "found_identity_match"
    FOUND_IDENTITY_MISMATCH = "found_identity_mismatch"
    NOT_FOUND = "not_found"
    FAILED = "failed"
    NOT_ATTEMPTED = "not_attempted"


@dataclass(frozen=True, slots=True)
class InsertAttemptDiagnostic:
    outcome_class: InsertOutcomeClass
    exception_type: str | None = None
    http_status: int | None = None
    content_type: str | None = None
    decoded_type: str | None = None
    top_level_keys: tuple[str, ...] = ()
    has_id: bool = False
    has_status: bool = False
    has_html_link: bool = False
    has_error: bool = False
    provider_reason: str | None = None
    response_received: bool = False
    request_may_have_reached_server: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "outcome_class": self.outcome_class.value,
            "exception_type": self.exception_type,
            "http_status": self.http_status,
            "content_type": self.content_type,
            "decoded_type": self.decoded_type,
            "top_level_keys": list(self.top_level_keys),
            "has_id": self.has_id,
            "has_status": self.has_status,
            "has_htmlLink": self.has_html_link,
            "has_error": self.has_error,
            "provider_reason": self.provider_reason,
            "response_received": self.response_received,
            "request_may_have_reached_server": self.request_may_have_reached_server,
        }


@dataclass(frozen=True, slots=True)
class ReconciliationAttemptDiagnostic:
    attempt: int
    http_status: int | None
    outcome: ReconciliationOutcome
    found: bool
    identity_match: bool | None
    exception_type: str | None = None
    provider_reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "attempt": self.attempt,
            "http_status": self.http_status,
            "outcome": self.outcome.value,
            "found": self.found,
            "identity_match": self.identity_match,
            "exception_type": self.exception_type,
            "provider_reason": self.provider_reason,
        }


@dataclass(frozen=True, slots=True)
class ReconciliationDiagnostic:
    get_attempt_count: int
    attempts: tuple[ReconciliationAttemptDiagnostic, ...]
    final_outcome: ReconciliationOutcome

    def as_dict(self) -> dict[str, object]:
        return {
            "get_attempt_count": self.get_attempt_count,
            "attempts": [attempt.as_dict() for attempt in self.attempts],
            "final_outcome": self.final_outcome.value,
        }


def diagnostic_bundle(
    insert_attempt: InsertAttemptDiagnostic | None,
    reconciliation: ReconciliationDiagnostic | None,
) -> dict[str, object]:
    return {
        "insert_attempt": (
            insert_attempt.as_dict() if insert_attempt is not None else None
        ),
        "reconciliation": (
            reconciliation.as_dict() if reconciliation is not None else None
        ),
    }


def sanitized_text(value: Any, *, limit: int = 512) -> str | None:
    """Keep exception/provider messages useful without retaining secrets or URLs."""

    if value is None:
        return None
    text = str(value)
    text = re.sub(r"(?i)bearer\s+\S+", "Bearer <redacted>", text)
    text = re.sub(
        r"(?i)(authorization|access[_ -]?token|refresh[_ -]?token|client[_ -]?secret|password|api[_ -]?key)\s*[:=]\s*\S+",
        r"\1=<redacted>",
        text,
    )
    text = re.sub(r"https?://\S+", "<url>", text)
    return text[:limit]
