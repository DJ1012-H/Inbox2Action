from __future__ import annotations

import pytest
from pydantic import ValidationError

from inbox2action.memory import (
    CalendarPreferences,
    MemoryCategory,
    MemoryDocument,
    ReplyPreferences,
    TaskPreferences,
    UserEditDiff,
    memory_owner_id,
)


def test_user_edit_diff_is_typed_and_deterministic() -> None:
    diff = UserEditDiff.from_action_edit(
        thread_id="email:0123456789abcdef01234567",
        action_id="task-1",
        approval_revision=2,
        before_parameters={
            "title": "Prepare report",
            "description": "Summarize results",
            "priority": "medium",
        },
        after_parameters={
            "title": "Prepare report",
            "description": "Summarize results",
            "priority": "high",
        },
        tool_name="save_task_proposal",
    )

    assert diff.category is MemoryCategory.TASK
    assert diff.before == {"priority": "medium"}
    assert diff.after == {"priority": "high"}
    assert diff.changed_fields == ("priority",)
    assert diff.preference_updates == {"default_priority": "high"}
    assert diff.evidence_id == diff.evidence_id


def test_reply_diff_stores_features_not_raw_body() -> None:
    diff = UserEditDiff.from_action_edit(
        thread_id="email:0123456789abcdef01234567",
        action_id="reply-1",
        approval_revision=1,
        before_parameters={"subject": "Re: Hello", "body": "Hi. Got it."},
        after_parameters={
            "subject": "Re: Hello",
            "body": "尊敬的团队，\n请审阅这份更新。谢谢",
        },
        tool_name="save_reply_draft",
    )

    assert diff.category is MemoryCategory.REPLY
    assert "Dear team" not in str(diff.after)
    assert "language" in diff.preference_updates
    assert "formality" in diff.preference_updates


def test_memory_documents_reject_provider_targets_and_timezone() -> None:
    with pytest.raises(ValidationError):
        TaskPreferences.model_validate(
            {"default_priority": "high", "clickup_list_id": "123"}
        )
    with pytest.raises(ValidationError):
        CalendarPreferences.model_validate(
            {"preferred_duration_minutes": 30, "timezone": "UTC"}
        )
    with pytest.raises(ValidationError):
        MemoryDocument(
            category=MemoryCategory.TASK,
            version=0,
            evidence_count=0,
            preferences={"clickup_list_id": "123"},
        )


def test_owner_namespace_identity_is_normalized_but_not_replaced() -> None:
    assert memory_owner_id(" Alice@Example.TEST ") == "alice@example.test"
    assert ReplyPreferences().model_dump(mode="json") == {
        "language": None,
        "formality": None,
        "length": None,
        "opening_style": None,
        "closing_style": None,
        "expression_patterns": [],
    }
