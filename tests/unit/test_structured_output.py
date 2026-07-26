from __future__ import annotations

import hashlib

import pytest

from inbox2action.errors import ModelOutputValidationError
from inbox2action.llm.models import ChatCompletionResult, TriageDecision
from inbox2action.llm.structured_output import (
    parse_email_triage_content,
    parse_email_triage_response,
)


def response(content: str | None) -> ChatCompletionResult:
    return ChatCompletionResult(
        model="deepseek-v4-flash",
        content=content,
        finish_reason="stop",
        prompt_tokens=1,
        completion_tokens=2,
        total_tokens=3,
    )


def test_valid_json_maps_to_strict_pydantic_model() -> None:
    result = parse_email_triage_response(
        response('{"decision":"NOTIFY","reason":"需要人工确认","confidence":0.8}')
    )

    assert result.decision is TriageDecision.NOTIFY
    assert result.confidence == 0.8


@pytest.mark.parametrize(
    "content,error_type",
    [
        (None, "empty_content"),
        ("", "empty_content"),
        ("not-json", "invalid_json"),
        ("[]", "json_not_object"),
        ('{"decision":"NOTIFY"}', "schema_validation"),
        (
            '{"decision":"NOTIFY","reason":"ok","confidence":0.5,"extra":1}',
            "schema_validation",
        ),
        (
            '{"decision":"SEND","reason":"ok","confidence":0.5}',
            "schema_validation",
        ),
        (
            '{"decision":"NOTIFY","reason":"ok","confidence":1.1}',
            "schema_validation",
        ),
        ('{"decision":"NOTIFY","reason":"","confidence":0.5}', "schema_validation"),
    ],
)
def test_invalid_structured_output_is_rejected_without_raw_content(
    content: str | None,
    error_type: str,
) -> None:
    with pytest.raises(ModelOutputValidationError) as captured:
        parse_email_triage_content(content)

    error = captured.value
    assert error.metadata is not None
    assert error.metadata.error_type == error_type
    assert (
        error.metadata.content_sha256
        == hashlib.sha256((content or "").encode("utf-8")).hexdigest()
    )
    assert not content or content not in str(error)
