from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from inbox2action.calendar import (
    CalendarToolRuntime,
    FixtureFreeBusyAdapter,
    GoogleCalendarFreeBusyAdapter,
    GoogleCalendarWriteExecutor,
)
from inbox2action.calendar.errors import (
    GoogleCalendarConflictError,
    GoogleCalendarInvalidResponseError,
    GoogleCalendarTransportError,
)
from inbox2action.evaluation.policy_v3 import (
    ActionNodeV3,
    ActionPlanV3,
    ParameterResolutionStatus,
    ParameterResolutionV3,
)
from inbox2action.evaluation.triage_v3 import TriageResultV3
from inbox2action.llm.models import ChatCompletionResult, ToolCall, TriageDecision
from inbox2action.stage3 import (
    ActionProposal,
    EmailEnvelope,
    InMemoryExecutionLedger,
    Stage2PlanningBundle,
    build_email_action_graph,
    prepare_workflow_state,
    workflow_state_to_graph,
)
from inbox2action.stage8 import CalendarActionAgent, extract_authorized_intervals
from inbox2action.tools.schemas import CheckCalendarAvailabilityArgs

TZ = ZoneInfo("Asia/Shanghai")
A_START = datetime(2026, 8, 21, 15, 0, tzinfo=TZ)
A_END = datetime(2026, 8, 21, 16, 0, tzinfo=TZ)
B_START = datetime(2026, 8, 21, 16, 0, tzinfo=TZ)
B_END = datetime(2026, 8, 21, 17, 0, tzinfo=TZ)


class FakeFreeBusyClient:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def query_freebusy(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(kwargs)
        return self.response


def _freebusy_response(*busy: tuple[str, str]) -> dict[str, object]:
    return {
        "calendars": {
            "trusted-calendar@example.com": {
                "busy": [{"start": start, "end": end} for start, end in busy]
            }
        }
    }


def test_freebusy_free_busy_and_trusted_calendar_timezone() -> None:
    client = FakeFreeBusyClient(_freebusy_response())
    adapter = GoogleCalendarFreeBusyAdapter(
        client, calendar_id="trusted-calendar@example.com"
    )
    free = adapter.check(start=A_START, end=A_END, timezone="Asia/Shanghai")

    assert free.available is True
    assert client.calls[0]["calendar_id"] == "trusted-calendar@example.com"
    assert client.calls[0]["timezone"] == "Asia/Shanghai"

    client.response = _freebusy_response(
        ("2026-08-21T15:00:00+08:00", "2026-08-21T16:00:00+08:00"),
    )
    busy = adapter.check(start=A_START, end=A_END, timezone="Asia/Shanghai")
    assert busy.available is False
    assert len(busy.busy_intervals) == 1


def test_explicit_chinese_alternatives_are_whitelisted_without_fixed_slot_jump() -> None:
    intervals = extract_authorized_intervals(
        "8 月 21 日下午 3 点召开项目评审，预计 1 小时。如果下午 3 点不方便，下午 4 点也可以。",
        current_time="2026-08-19T09:00:00+08:00",
        timezone="Asia/Shanghai",
    )
    assert intervals == ((A_START, A_END), (B_START, B_END))


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"calendars": {"trusted-calendar@example.com": {"busy": [{}]}}},
        {"calendars": {"trusted-calendar@example.com": {"busy": "bad"}}},
    ],
)
def test_malformed_freebusy_response_fails_closed(response: dict[str, object]) -> None:
    adapter = GoogleCalendarFreeBusyAdapter(
        FakeFreeBusyClient(response), calendar_id="trusted-calendar@example.com"
    )
    with pytest.raises(GoogleCalendarInvalidResponseError):
        adapter.check(start=A_START, end=A_END, timezone="Asia/Shanghai")


def test_naive_and_invalid_intervals_are_rejected_before_provider_call() -> None:
    client = FakeFreeBusyClient(_freebusy_response())
    with pytest.raises(ValueError):
        CheckCalendarAvailabilityArgs(
            start="2026-08-21T15:00:00",
            end="2026-08-21T16:00:00+08:00",
        )
    with pytest.raises(ValueError):
        CheckCalendarAvailabilityArgs(start=A_END, end=A_START)
    assert client.calls == []


def _tool_response(name: str, call_id: str, arguments: dict[str, object]) -> ChatCompletionResult:
    return ChatCompletionResult(
        model="deepseek-v4-flash",
        content=None,
        finish_reason="tool_calls",
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
        tool_calls=(
            ToolCall(call_id, name, json.dumps(arguments, ensure_ascii=False)),
        ),
    )


class ScriptedCalendarModel:
    def __init__(self, *responses: ChatCompletionResult) -> None:
        self.responses = list(responses)
        self.messages: list[list[dict[str, object]]] = []

    def complete(self, messages: Any, **_: object) -> ChatCompletionResult:
        self.messages.append([dict(message) for message in messages])
        return self.responses.pop(0)


def test_agent_consumes_busy_observation_and_uses_authorized_free_alternative() -> None:
    adapter = FixtureFreeBusyAdapter(busy_intervals=((A_START, A_END),))
    runtime = CalendarToolRuntime(
        adapter,
        authorized_intervals=((A_START, A_END), (B_START, B_END)),
    )
    model = ScriptedCalendarModel(
        _tool_response(
            "check_calendar_availability",
            "check-a",
            {"start": A_START.isoformat(), "end": A_END.isoformat()},
        ),
        _tool_response(
            "check_calendar_availability",
            "check-b",
            {"start": B_START.isoformat(), "end": B_END.isoformat()},
        ),
        _tool_response(
            "save_calendar_proposal",
            "proposal-b",
            {
                "summary": "项目评审",
                "description": "评审材料",
                "start_time": B_START.isoformat(),
                "end_time": B_END.isoformat(),
                "timezone": "Asia/Shanghai",
            },
        ),
        _tool_response("done", "done", {"summary": "已准备日历提案"}),
    )
    result = CalendarActionAgent(model, runtime).run(
        {"subject": "项目评审", "sanitized_body": "15点或16点均可"},
        current_time="2026-08-19T09:00:00+08:00",
    )

    assert [entry.status for entry in result.trace] == [
        "conflict",
        "ok",
        "proposal_created",
        "complete",
    ]
    assert result.calendar_proposals[0].start_time == B_START
    assert any("available" in str(message.get("content")) for message in model.messages[2])
    assert adapter.call_count == 2


def test_busy_without_authorized_alternative_asks_user_and_never_proposes() -> None:
    adapter = FixtureFreeBusyAdapter(busy_intervals=((A_START, A_END),))
    runtime = CalendarToolRuntime(adapter, authorized_intervals=((A_START, A_END),))
    model = ScriptedCalendarModel(
        _tool_response(
            "check_calendar_availability",
            "check-a",
            {"start": A_START.isoformat(), "end": A_END.isoformat()},
        ),
        _tool_response("ask_user", "ask", {"question": "请提供其他授权时间"}),
        _tool_response("done", "done", {"summary": "等待时间确认"}),
    )
    result = CalendarActionAgent(model, runtime).run(
        {"subject": "项目评审", "sanitized_body": "15点"},
        current_time="2026-08-19T09:00:00+08:00",
    )
    assert result.calendar_proposals == ()
    assert [entry.tool_name for entry in result.trace] == [
        "check_calendar_availability",
        "ask_user",
        "done",
    ]


class FakeEventClient:
    def __init__(self, *, timeout: bool = False, mismatch: bool = False) -> None:
        self.timeout = timeout
        self.mismatch = mismatch
        self.insert_count = 0
        self.get_count = 0
        self.event: dict[str, object] | None = None

    def insert_event(self, *, calendar_id: str, event_id: str, body: dict[str, object]) -> dict[str, object]:
        assert calendar_id == "trusted-calendar@example.com"
        self.insert_count += 1
        if self.timeout:
            self.event = dict(body)
            self.event["id"] = event_id
            raise GoogleCalendarTransportError()
        if self.mismatch:
            raise GoogleCalendarConflictError()
        self.event = dict(body)
        self.event["id"] = event_id
        return self.event

    def get_event(self, *, calendar_id: str, event_id: str) -> dict[str, object]:
        assert calendar_id == "trusted-calendar@example.com"
        self.get_count += 1
        if self.mismatch:
            return {
                "id": event_id,
                "extendedProperties": {
                    "private": {"i2a_k": "other", "i2a_h": "other", "i2a_a": "other"}
                },
            }
        if self.event is None:
            raise AssertionError("event not configured")
        return self.event


def _calendar_permit() -> Any:
    proposal = ActionProposal(
        action_id="calendar-action-1",
        tool_name="save_calendar_proposal",
        parameters={
            "summary": "项目评审",
            "description": "评审材料",
            "start_time": B_START,
            "end_time": B_END,
            "timezone": "Asia/Shanghai",
            "location": None,
        },
    )
    triage = TriageResultV3(
        decision=TriageDecision.ACTION_REQUIRED,
        reason="calendar",
        confidence=1.0,
        suspected_prompt_injection=False,
        security_reason=None,
        safe_to_plan_actions=True,
    )
    action = ActionNodeV3(
        action_id=proposal.action_id,
        tool_name=proposal.tool_name,
        required_parameters=("summary", "start_time", "end_time", "timezone"),
        parameter_resolutions=tuple(
            ParameterResolutionV3(
                field_name=name,
                status=ParameterResolutionStatus.RESOLVED,
                source="test",
            )
            for name in ("summary", "start_time", "end_time", "timezone")
        ),
        requires_approval=True,
    )
    state = prepare_workflow_state(
        EmailEnvelope(
            account_id="calendar-account",
            message_id="calendar-message",
            subject="项目评审",
            body="请安排项目评审。",
        ),
        Stage2PlanningBundle(
            triage=triage,
            action_plan=ActionPlanV3(actions=(action,)),
            proposals=[proposal],
        ),
    )
    return state


@pytest.mark.asyncio
async def test_hitl_revision_guard_and_approved_write_are_shared_with_stage7() -> None:
    client = FakeEventClient()
    executor = GoogleCalendarWriteExecutor(
        client,
        calendar_id="trusted-calendar@example.com",
        enabled=True,
    )
    state = _calendar_permit()
    graph = build_email_action_graph(
        checkpointer=InMemorySaver(),
        execution_ledger=InMemoryExecutionLedger(),
        write_executor=executor,
    )
    config = {"configurable": {"thread_id": state.thread_id}}
    first = await graph.ainvoke(workflow_state_to_graph(state), config)
    assert first["__interrupt__"][0].value["revision"] == 1
    from inbox2action.stage6.approval import ApprovalService, ApprovalServiceError
    from inbox2action.stage6.index import InMemoryWorkflowIndex

    index = InMemoryWorkflowIndex()
    await index.reserve(
        thread_id=state.thread_id,
        account_id="calendar-account",
        message_id="calendar-message",
        from_address=None,
        subject="项目评审",
        received_at=None,
    )
    await index.set_status(state.thread_id, "waiting_for_approval")
    approval = ApprovalService(graph, index)
    edited = await approval.decide(
        state.thread_id,
        operation="edit",
        expected_revision=1,
        action_id="calendar-action-1",
        parameters={
            "summary": "编辑后的评审",
            "description": "编辑",
            "start_time": B_START.isoformat(),
            "end_time": B_END.isoformat(),
            "timezone": "Asia/Shanghai",
            "location": None,
        },
    )
    assert edited["approval_revision"] == 2
    with pytest.raises(ApprovalServiceError, match="stale_approval"):
        await approval.decide(
            state.thread_id,
            operation="approve",
            expected_revision=1,
            action_id="calendar-action-1",
        )
    completed = await approval.decide(
        state.thread_id,
        operation="approve",
        expected_revision=2,
        action_id="calendar-action-1",
    )
    assert completed["status"] == "completed"
    assert client.insert_count == 1
    assert completed["actions"][0]["result"]["resource"] == {
        "provider": "google_calendar",
        "resource_type": "event",
        "resource_id": completed["actions"][0]["result"]["resource"]["resource_id"],
        "url": None,
    }


@pytest.mark.asyncio
async def test_deterministic_id_timeout_reconciles_without_blind_retry() -> None:
    client = FakeEventClient(timeout=True)
    executor = GoogleCalendarWriteExecutor(
        client,
        calendar_id="trusted-calendar@example.com",
        enabled=True,
    )
    state = _calendar_permit()
    from inbox2action.stage3.contracts import (
        ActionStatus,
        ApprovalRecord,
        ApprovalStatus,
        payload_hash,
    )
    from inbox2action.stage3.workflow import authorize_execution

    proposal = state.actions[0].proposal
    digest = payload_hash(proposal)
    approved = state.actions[0].model_copy(
        update={
            "status": ActionStatus.APPROVED,
            "approval": ApprovalRecord(
                action_id=proposal.action_id,
                revision=1,
                status=ApprovalStatus.APPROVED,
                payload_hash=digest,
                approved_payload_hash=digest,
            ),
        }
    )
    permit = authorize_execution(
        state.model_copy(
            update={
                "actions": [approved],
                "current_action_id": proposal.action_id,
            }
        ),
        proposal.action_id,
    )
    result = await executor.execute(permit)
    assert result.status == "succeeded"
    assert client.insert_count == 1
    assert client.get_count == 1


@pytest.mark.asyncio
async def test_duplicate_event_identity_mismatch_fails_closed() -> None:
    client = FakeEventClient(mismatch=True)
    executor = GoogleCalendarWriteExecutor(
        client,
        calendar_id="trusted-calendar@example.com",
        enabled=True,
    )
    state = _calendar_permit()
    from inbox2action.stage3.contracts import (
        ActionStatus,
        ApprovalRecord,
        ApprovalStatus,
        payload_hash,
    )
    from inbox2action.stage3.workflow import authorize_execution

    proposal = state.actions[0].proposal
    digest = payload_hash(proposal)
    approved = state.actions[0].model_copy(
        update={
            "status": ActionStatus.APPROVED,
            "approval": ApprovalRecord(
                action_id=proposal.action_id,
                revision=1,
                status=ApprovalStatus.APPROVED,
                payload_hash=digest,
                approved_payload_hash=digest,
            ),
        }
    )
    permit = authorize_execution(
        state.model_copy(update={"actions": [approved]}), proposal.action_id
    )
    result = await executor.execute(permit)
    assert result.status == "failed"
    assert result.error_code == "google_calendar_identity_mismatch"
    assert client.insert_count == 1
    assert client.get_count == 1
