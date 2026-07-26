from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import ValidationError

from inbox2action.errors import FailureMetadata, ModelOutputValidationError
from inbox2action.llm.models import ChatCompletionResult, EmailTriageResult


def parse_email_triage_response(
    response: ChatCompletionResult,
) -> EmailTriageResult:
    return parse_email_triage_content(response.content)


def parse_email_triage_content(content: str | None) -> EmailTriageResult:
    safe_content = content if isinstance(content, str) else ""
    if not safe_content.strip():
        raise ModelOutputValidationError(
            "Model output content is empty.",
            metadata=_metadata(safe_content, "empty_content"),
        )

    try:
        payload: Any = json.loads(safe_content)
    except json.JSONDecodeError as exc:
        raise ModelOutputValidationError(
            "Model output is not valid JSON.",
            metadata=_metadata(safe_content, "invalid_json"),
        ) from exc

    if not isinstance(payload, dict):
        raise ModelOutputValidationError(
            "Structured output must be a JSON object.",
            metadata=_metadata(safe_content, "json_not_object"),
        )

    try:
        return EmailTriageResult.model_validate(payload)
    except ValidationError as exc:
        raise ModelOutputValidationError(
            "Structured output failed the EmailTriageResult schema.",
            metadata=_metadata(safe_content, "schema_validation"),
        ) from exc


def _metadata(content: str, error_type: str) -> FailureMetadata:
    encoded = content.encode("utf-8")
    return FailureMetadata(
        error_type=error_type,
        content_length=len(encoded),
        content_sha256=hashlib.sha256(encoded).hexdigest(),
    )
