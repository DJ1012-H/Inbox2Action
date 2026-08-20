from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from inbox2action.llm.models import ChatCompletionResult, ToolCall
from inbox2action.memory import MemoryCategory, MemoryService, UserEditDiff
from inbox2action.stage3.contracts import EmailEnvelope
from inbox2action.stage6 import GmailStage2Planner


@dataclass(frozen=True)
class _Item:
    value: dict[str, Any]


class _Store:
    def __init__(self) -> None:
        self.values: dict[tuple[tuple[str, ...], str], dict[str, Any]] = {}

    async def aget(
        self, namespace: tuple[str, ...], key: str, **_: Any
    ) -> _Item | None:
        value = self.values.get((namespace, key))
        return _Item(dict(value)) if value is not None else None

    async def aput(
        self,
        namespace: tuple[str, ...],
        key: str,
        value: dict[str, Any],
        **_: Any,
    ) -> None:
        self.values[(namespace, key)] = dict(value)

    async def asearch(self, namespace: tuple[str, ...], **_: Any) -> list[_Item]:
        return [
            _Item(dict(value))
            for (stored_namespace, _), value in self.values.items()
            if stored_namespace == namespace
            and value.get("record_type") == "memory_evidence"
        ]


class _SameModel:
    """The A/B model is identical; only planner context is allowed to differ."""

    def __init__(self) -> None:
        self.messages: list[list[dict[str, object]]] = []

    def complete(
        self,
        messages: list[dict[str, object]],
        *,
        response_format: dict[str, object] | None = None,
        tools: list[dict[str, object]] | None = None,
    ) -> ChatCompletionResult:
        del tools
        self.messages.append(messages)
        if response_format is not None:
            content = json.dumps(
                {
                    "decision": "ACTION_REQUIRED",
                    "reason": "reply requested",
                    "confidence": 1.0,
                    "suspected_prompt_injection": False,
                    "security_reason": None,
                    "safe_to_plan_actions": True,
                }
            )
            return ChatCompletionResult(
                model="same-fake-model",
                content=content,
                finish_reason="stop",
                prompt_tokens=1,
                completion_tokens=1,
                total_tokens=2,
            )
        return ChatCompletionResult(
            model="same-fake-model",
            content=None,
            finish_reason="tool_calls",
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            tool_calls=(
                ToolCall(
                    id="reply-1",
                    name="save_reply_draft",
                    arguments=json.dumps(
                        {
                            "recipient": "sender@example.test",
                            "subject": "Re: Request",
                            "body": "Prepared draft.",
                        }
                    ),
                ),
            ),
        )


def _diff(
    category: MemoryCategory,
    *,
    before: dict[str, object],
    after: dict[str, object],
    updates: dict[str, object],
    action_id: str,
) -> UserEditDiff:
    return UserEditDiff(
        category=category,
        thread_id="email:0123456789abcdef01234567",
        action_id=action_id,
        approval_revision=1,
        before=before,
        after=after,
        preference_updates=updates,
    )


@pytest.mark.asyncio
async def test_fixed_memory_ab_covers_all_categories_and_same_model() -> None:
    service = MemoryService(_Store())
    diffs = (
        _diff(
            MemoryCategory.TRIAGE,
            before={"decision": "NOTIFY", "message_type": "newsletter"},
            after={"decision": "IGNORE", "message_type": "newsletter"},
            updates={"decision": "IGNORE", "message_type": "newsletter"},
            action_id="triage",
        ),
        _diff(
            MemoryCategory.REPLY,
            before={"language": "en"},
            after={"language": "zh"},
            updates={"language": "zh"},
            action_id="reply",
        ),
        _diff(
            MemoryCategory.TASK,
            before={"priority": "medium"},
            after={"priority": "high"},
            updates={"default_priority": "high"},
            action_id="task",
        ),
        _diff(
            MemoryCategory.CALENDAR,
            before={"duration_minutes": 60},
            after={"duration_minutes": 30},
            updates={"preferred_duration_minutes": 30},
            action_id="calendar",
        ),
    )
    for diff in diffs:
        await service.apply_user_edit("account@example.test", diff)

    off = {"memory_role": "soft_preference_only"}
    on = (await service.load_context("account@example.test")).to_prompt_context()
    assert off != on
    assert on["triage_preferences"]["ignored_types"] == ["newsletter"]
    assert on["reply_preferences"]["language"] == "zh"
    assert on["task_preferences"]["default_priority"] == "high"
    assert on["calendar_preferences"]["preferred_duration_minutes"] == 30

    off_model = _SameModel()
    on_model = _SameModel()
    envelope = EmailEnvelope(
        account_id="account@example.test",
        message_id="new-thread-message",
        from_address="sender@example.test",
        subject="Request",
        body="Please prepare a reply.",
    )
    off_bundle = GmailStage2Planner(off_model).plan(envelope)
    on_bundle = await GmailStage2Planner(
        on_model, memory_service=service
    ).plan_with_memory(envelope)
    assert off_bundle.proposals[0].tool_name == on_bundle.proposals[0].tool_name
    on_triage_payload = json.loads(on_model.messages[0][1]["content"])
    assert (
        on_triage_payload["TRUSTED CONTEXT"]["user_context"]
        ["LONG_TERM_SOFT_PREFERENCES"]["reply_preferences"]["language"]
        == "zh"
    )
    assert "LONG_TERM_SOFT_PREFERENCES" not in json.loads(
        off_model.messages[0][1]["content"]
    )["TRUSTED CONTEXT"]["user_context"]
