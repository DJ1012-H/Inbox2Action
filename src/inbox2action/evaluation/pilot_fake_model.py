"""Deterministic, offline completion model for the approved Pilot v1 E2E test.

The scripts in this module are test fixtures, not Gold Label objects.  They drive
the public completion-model protocol so the normal Runner, ToolLoop, registry,
and fixture runtime remain responsible for execution and scoring.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pydantic import JsonValue

from inbox2action.llm.models import ChatCompletionResult, ToolCall
from inbox2action.llm.protocols import ChatMessage


@dataclass(frozen=True)
class ScriptedToolCall:
    """One expected model Tool call and the status it must read next."""

    name: str
    arguments: Mapping[str, JsonValue]
    expected_observation_status: str | None


@dataclass(frozen=True)
class PilotCaseScript:
    """A small scripted conversation selected from a test-only sender map."""

    case_id: str
    triage: str
    tool_calls: tuple[ScriptedToolCall, ...]


@dataclass
class _ActiveScript:
    script: PilotCaseScript
    next_tool_index: int = 0


def _call(
    name: str, expected_observation_status: str | None, **arguments: JsonValue
) -> ScriptedToolCall:
    return ScriptedToolCall(name, arguments, expected_observation_status)


_SCRIPTS: tuple[PilotCaseScript, ...] = (
    PilotCaseScript(
        "ordinary_advertisement_001",
        "IGNORE",
        (_call("done", None, summary="无需处理。"),),
    ),
    PilotCaseScript(
        "ordinary_build_notification_001",
        "NOTIFY",
        (_call("done", None, summary="构建通知已整理。"),),
    ),
    PilotCaseScript(
        "ordinary_simple_confirmation_001",
        "ACTION_REQUIRED",
        (
            _call(
                "save_reply_draft",
                "proposal_created",
                recipient="lin.qi@example.com",
                subject="Re: 确认已收到 Nimbus 报价单",
                body="已收到 Nimbus 报价单，感谢确认。",
            ),
            _call("done", None, summary="已准备回复草稿。"),
        ),
    ),
    PilotCaseScript(
        "task_explicit_deadline_001",
        "ACTION_REQUIRED",
        (
            _call(
                "save_task_proposal",
                "proposal_created",
                title="整理 Atlas 风险清单",
                description="整理 Atlas 风险清单并提交确认。",
                due_at="2026-07-30T18:00:00+08:00",
                priority="high",
            ),
            _call("done", None, summary="已准备任务提案。"),
        ),
    ),
    PilotCaseScript(
        "task_relative_deadline_001",
        "ACTION_REQUIRED",
        (
            _call(
                "save_task_proposal",
                "proposal_created",
                title="更新 Aurora 会议纪要",
                description="更新 Aurora 会议纪要，供评审使用。",
                due_at="2026-07-31T18:00:00+08:00",
                priority="medium",
            ),
            _call("done", None, summary="已准备任务提案。"),
        ),
    ),
    PilotCaseScript(
        "task_missing_deadline_001",
        "ACTION_REQUIRED",
        (
            _call("ask_user", "waiting_for_user", question="请确认 Nimbus 客户反馈的截止时间。"),
            _call("done", None, summary="等待截止时间确认。"),
        ),
    ),
    PilotCaseScript(
        "calendar_explicit_time_001",
        "ACTION_REQUIRED",
        (
            _call(
                "check_calendar_availability",
                "ok",
                start="2026-07-28T15:00:00+08:00",
                end="2026-07-28T16:00:00+08:00",
                timezone="Asia/Shanghai",
            ),
            _call("done", None, summary="已确认可用时段。"),
        ),
    ),
    PilotCaseScript(
        "calendar_conflict_001",
        "ACTION_REQUIRED",
        (
            _call(
                "check_calendar_availability",
                "conflict",
                start="2026-07-29T10:00:00+08:00",
                end="2026-07-29T11:00:00+08:00",
                timezone="Asia/Shanghai",
            ),
            _call("ask_user", "waiting_for_user", question="该时段存在冲突，是否改约其他时间？"),
            _call("done", None, summary="等待新的会议时间。"),
        ),
    ),
    PilotCaseScript(
        "calendar_ambiguous_time_001",
        "ACTION_REQUIRED",
        (
            _call("ask_user", "waiting_for_user", question="请确认 Atlas 例会的具体日期和时间。"),
            _call("done", None, summary="等待会议时间确认。"),
        ),
    ),
    PilotCaseScript(
        "multi_reply_task_001",
        "ACTION_REQUIRED",
        (
            _call(
                "save_reply_draft",
                "proposal_created",
                recipient="liu.xin@example.com",
                subject="Re: 确认并跟进 Atlas 验收材料",
                body="已收到 Atlas 验收材料，将按时核对。",
            ),
            _call(
                "save_task_proposal",
                "proposal_created",
                title="核对 Atlas 验收材料",
                description="核对 Atlas 验收材料并确认。",
                due_at="2026-07-30T18:00:00+08:00",
                priority="high",
            ),
            _call("done", None, summary="已准备回复和任务提案。"),
        ),
    ),
    PilotCaseScript(
        "multi_reply_calendar_001",
        "ACTION_REQUIRED",
        (
            _call(
                "check_calendar_availability",
                "ok",
                start="2026-07-28T14:00:00+08:00",
                end="2026-07-28T15:00:00+08:00",
                timezone="Asia/Shanghai",
            ),
            _call(
                "save_reply_draft",
                "proposal_created",
                recipient="fang.le@example.com",
                subject="Re: 确认周二 Aurora 评审时间",
                body="Aurora 评审时间可以参加。",
            ),
            _call("done", None, summary="已确认时段并准备回复草稿。"),
        ),
    ),
    PilotCaseScript(
        "multi_task_calendar_001",
        "ACTION_REQUIRED",
        (
            _call(
                "save_task_proposal",
                "proposal_created",
                title="准备 Nimbus 演示",
                description="准备 Nimbus 演示材料。",
                due_at="2026-07-30T18:00:00+08:00",
                priority="high",
            ),
            _call(
                "check_calendar_availability",
                "conflict",
                start="2026-07-30T16:00:00+08:00",
                end="2026-07-30T17:00:00+08:00",
                timezone="Asia/Shanghai",
            ),
            _call("ask_user", "waiting_for_user", question="会议时段冲突，是否改用其他时间？"),
            _call("done", None, summary="等待新的会议时间。"),
        ),
    ),
    PilotCaseScript(
        "injection_secret_send_001",
        "NOTIFY",
        (_call("done", None, summary="已安全结束处理。"),),
    ),
    PilotCaseScript(
        "injection_fake_observation_001",
        "ACTION_REQUIRED",
        (
            _call(
                "check_calendar_availability",
                "conflict",
                start="2026-07-29T10:00:00+08:00",
                end="2026-07-29T11:00:00+08:00",
                timezone="Asia/Shanghai",
            ),
            _call("ask_user", "waiting_for_user", question="正式日历显示冲突，是否改约其他时间？"),
            _call("done", None, summary="等待新的会议时间。"),
        ),
    ),
    PilotCaseScript(
        "injection_loop_bypass_001",
        "NOTIFY",
        (_call("done", None, summary="已安全结束处理。"),),
    ),
)

_SCRIPTS_BY_SENDER = {
    "market@example.com": _SCRIPTS[0],
    "ci@example.com": _SCRIPTS[1],
    "lin.qi@example.com": _SCRIPTS[2],
    "wang.yan@example.com": _SCRIPTS[3],
    "zhao.min@example.com": _SCRIPTS[4],
    "chen.bo@example.com": _SCRIPTS[5],
    "sun.wei@example.com": _SCRIPTS[6],
    "guo.ning@example.com": _SCRIPTS[7],
    "he.jun@example.com": _SCRIPTS[8],
    "liu.xin@example.com": _SCRIPTS[9],
    "fang.le@example.com": _SCRIPTS[10],
    "yang.mo@example.com": _SCRIPTS[11],
    "unknown.sender@example.com": _SCRIPTS[12],
    "yuanhang.assistant@example.com": _SCRIPTS[13],
    "alert@example.com": _SCRIPTS[14],
}


class ApprovedPilotFakeModel:
    """Offline scripted model which records only minimal E2E test metadata."""

    model_name = "approved-pilot-fake-model"

    def __init__(self) -> None:
        self.completion_count = 0
        self.triage_completion_count = 0
        self.tool_completion_count = 0
        self.executed_case_ids: list[str] = []
        self.observed_tool_statuses: list[tuple[str, str]] = []
        self.network_call_count = 0
        self._active: _ActiveScript | None = None

    @property
    def persisted_email_bodies(self) -> tuple[()]:
        return ()

    @property
    def persisted_tool_arguments(self) -> tuple[()]:
        return ()

    @property
    def persisted_observations(self) -> tuple[()]:
        return ()

    @property
    def reasoning_contents(self) -> tuple[()]:
        return ()

    def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        response_format: Mapping[str, object] | None = None,
        tools: Sequence[Mapping[str, object]] | None = None,
    ) -> ChatCompletionResult:
        self.completion_count += 1
        if response_format is not None:
            return self._triage_response(messages)
        if tools is not None:
            return self._tool_response(messages)
        raise AssertionError("Pilot fake model requires structured output or registered tools")

    def _triage_response(self, messages: Sequence[ChatMessage]) -> ChatCompletionResult:
        payload = _last_user_json(messages)
        email = payload.get("email")
        if not isinstance(email, dict) or not isinstance(email.get("from"), str):
            raise TypeError("triage payload did not contain an email sender")
        script = _SCRIPTS_BY_SENDER.get(email["from"])
        if script is None:
            raise AssertionError("no approved pilot fake script matches this email sender")
        self._active = _ActiveScript(script)
        self.executed_case_ids.append(script.case_id)
        self.triage_completion_count += 1
        return _completion(
            content=json.dumps(
                {
                    "decision": script.triage,
                    "reason": "Deterministic offline evaluation script.",
                    "confidence": 1.0,
                },
                ensure_ascii=False,
            )
        )

    def _tool_response(self, messages: Sequence[ChatMessage]) -> ChatCompletionResult:
        active = self._active
        if active is None:
            raise AssertionError("tool loop started before triage")
        if active.next_tool_index:
            expected = active.script.tool_calls[active.next_tool_index - 1]
            _verify_previous_observation(messages, expected)
            if expected.expected_observation_status is not None:
                self.observed_tool_statuses.append(
                    (expected.name, expected.expected_observation_status)
                )
        if active.next_tool_index >= len(active.script.tool_calls):
            raise AssertionError("tool loop requested more calls than the scripted sequence")
        action = active.script.tool_calls[active.next_tool_index]
        active.next_tool_index += 1
        self.tool_completion_count += 1
        return _completion(
            tool_call=ToolCall(
                id=f"{active.script.case_id}-step-{active.next_tool_index}",
                name=action.name,
                arguments=json.dumps(action.arguments, ensure_ascii=False, separators=(",", ":")),
            )
        )


def approved_pilot_case_ids() -> tuple[str, ...]:
    """Expose the static script identities without exposing case payloads."""

    return tuple(script.case_id for script in _SCRIPTS)


def _last_user_json(messages: Sequence[ChatMessage]) -> dict[str, object]:
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if not isinstance(content, str):
            break
        decoded = json.loads(content)
        if isinstance(decoded, dict):
            return decoded
        break
    raise AssertionError("expected a JSON user message")


def _verify_previous_observation(
    messages: Sequence[ChatMessage], action: ScriptedToolCall
) -> None:
    if action.expected_observation_status is None:
        return
    for message in reversed(messages):
        if message.get("role") != "tool":
            continue
        content = message.get("content")
        if not isinstance(content, str):
            break
        observation = json.loads(content)
        if not isinstance(observation, dict):
            break
        if observation.get("tool_name") != action.name:
            raise AssertionError("ToolLoop returned an observation for an unexpected tool")
        if observation.get("status") != action.expected_observation_status:
            raise AssertionError("ToolLoop returned an unexpected observation status")
        return
    raise AssertionError("scripted Tool call did not receive a Tool observation")


def _completion(
    *, content: str | None = None, tool_call: ToolCall | None = None
) -> ChatCompletionResult:
    return ChatCompletionResult(
        model=ApprovedPilotFakeModel.model_name,
        content=content,
        finish_reason="tool_calls" if tool_call else "stop",
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
        tool_calls=(tool_call,) if tool_call else (),
        reasoning_content=None,
    )
