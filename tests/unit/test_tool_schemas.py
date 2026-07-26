from __future__ import annotations

import pytest
from pydantic import ValidationError

from inbox2action.tools.schemas import (
    AskUserArgs,
    CheckCalendarAvailabilityArgs,
    DoneArgs,
    NoArguments,
    SaveReplyDraftArgs,
)


def test_calendar_args_require_explicit_timezone_and_use_taipei_default() -> None:
    arguments = CheckCalendarAvailabilityArgs(
        start="2026-07-27T09:00:00+08:00",
        end="2026-07-27T10:00:00+08:00",
    )

    assert arguments.timezone == "Asia/Taipei"


@pytest.mark.parametrize(
    "payload",
    [
        {
            "start": "2026-07-27T09:00:00",
            "end": "2026-07-27T10:00:00+08:00",
        },
        {
            "start": "2026-07-27T10:00:00+08:00",
            "end": "2026-07-27T09:00:00+08:00",
        },
        {
            "start": "2026-07-27T09:00:00+08:00",
            "end": "2026-07-28T18:00:00+08:00",
        },
        {
            "start": "2026-07-27T09:00:00+08:00",
            "end": "2026-07-27T10:00:00+08:00",
            "timezone": "Unknown/Zone",
        },
        {
            "start": "2026-07-27T09:00:00+08:00",
            "end": "2026-07-27T10:00:00+08:00",
            "extra": True,
        },
    ],
)
def test_calendar_business_rules_reject_unsafe_intervals(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        CheckCalendarAvailabilityArgs.model_validate(payload)


def test_control_and_draft_schemas_forbid_extra_fields() -> None:
    with pytest.raises(ValidationError):
        NoArguments.model_validate({"unexpected": True})
    with pytest.raises(ValidationError):
        AskUserArgs.model_validate({"question": "确认吗？", "extra": True})
    with pytest.raises(ValidationError):
        DoneArgs.model_validate({"summary": "完成", "extra": True})
    with pytest.raises(ValidationError):
        SaveReplyDraftArgs.model_validate(
            {"subject": "主题", "body": "正文", "extra": True}
        )
