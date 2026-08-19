from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from googleapiclient.errors import HttpError
from langgraph.checkpoint.memory import InMemorySaver

from inbox2action.calendar import (
    CalendarToolRuntime,
    FixtureFreeBusyAdapter,
    GoogleCalendarClient,
    GoogleCalendarFreeBusyAdapter,
    GoogleCalendarWriteExecutor,
    InsertOutcomeClass,
)
from inbox2action.calendar.errors import (
    GoogleCalendarApiError,
    GoogleCalendarConflictError,
    GoogleCalendarInvalidResponseError,
    GoogleCalendarLocalClientError,
    GoogleCalendarResponseDiagnostics,
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


class FakeHttpResponse(dict[str, object]):
    def __init__(self, status: int, content_type: str = "application/json") -> None:
        super().__init__({"content-type": content_type})
        self.status = status
        self.reason = "test response"


class FakeGoogleRequest:
    def __init__(
        self,
        response: object = None,
        *,
        error: Exception | None = None,
        http_response: FakeHttpResponse | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.http_response = (
            http_response
            if http_response is not None
            else getattr(error, "resp", None)
        )
        if self.http_response is None and error is None:
            self.http_response = FakeHttpResponse(200)
        self.response_callbacks: list[Any] = []

    def execute(self) -> object:
        for callback in self.response_callbacks:
            callback(self.http_response)
        if self.error is not None:
            raise self.error
        return self.response


class FakeGoogleCalendarService:
    def __init__(
        self,
        response: object = None,
        *,
        insert_error: Exception | None = None,
        get_response: object = None,
        get_errors: list[Exception] | None = None,
        get_responses: list[object] | None = None,
        get_script: list[object | Exception] | None = None,
        insert_construction_error: Exception | None = None,
    ) -> None:
        self.insert_count = 0
        self.get_count = 0
        self.insert_construction_error = insert_construction_error
        self.insert_request = FakeGoogleRequest(
            response,
            error=insert_error,
        )
        if get_script is not None:
            self.get_requests = [
                FakeGoogleRequest(error=item)
                if isinstance(item, Exception)
                else FakeGoogleRequest(item)
                for item in get_script
            ]
        elif get_responses is not None:
            self.get_requests = [FakeGoogleRequest(item) for item in get_responses]
        elif get_errors is not None:
            self.get_requests = [FakeGoogleRequest(error=item) for item in get_errors]
        else:
            self.get_requests = [
                FakeGoogleRequest(
                    get_response if get_response is not None else response,
                )
            ]
        self.insert_kwargs: dict[str, object] | None = None
        self.get_kwargs: dict[str, object] | None = None

    def events(self) -> FakeGoogleCalendarService:
        return self

    def insert(self, **kwargs: object) -> FakeGoogleRequest:
        self.insert_count += 1
        self.insert_kwargs = kwargs
        if self.insert_construction_error is not None:
            raise self.insert_construction_error
        return self.insert_request

    def get(self, **kwargs: object) -> FakeGoogleRequest:
        self.get_count += 1
        self.get_kwargs = kwargs
        if not self.get_requests:
            raise AssertionError("unexpected extra GET")
        return self.get_requests.pop(0)


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


def test_agent_repairs_one_provider_parallel_tool_response() -> None:
    adapter = FixtureFreeBusyAdapter()
    runtime = CalendarToolRuntime(
        adapter,
        authorized_intervals=((A_START, A_END),),
    )
    parallel = ChatCompletionResult(
        model="deepseek-v4-flash",
        content=None,
        finish_reason="tool_calls",
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
        tool_calls=(
            ToolCall(
                "parallel-a",
                "check_calendar_availability",
                json.dumps(
                    {
                        "start": A_START.isoformat(),
                        "end": A_END.isoformat(),
                    }
                ),
            ),
            ToolCall(
                "parallel-b",
                "check_calendar_availability",
                json.dumps(
                    {
                        "start": B_START.isoformat(),
                        "end": B_END.isoformat(),
                    }
                ),
            ),
        ),
    )
    model = ScriptedCalendarModel(
        parallel,
        _tool_response(
            "check_calendar_availability",
            "check-a",
            {"start": A_START.isoformat(), "end": A_END.isoformat()},
        ),
        _tool_response("ask_user", "ask", {"question": "请确认时间"}),
        _tool_response("done", "done", {"summary": "等待确认"}),
    )

    result = CalendarActionAgent(model, runtime).run(
        {"subject": "项目评审", "sanitized_body": "15点"},
        current_time="2026-08-19T09:00:00+08:00",
    )

    assert [entry.tool_name for entry in result.trace] == [
        "check_calendar_availability",
        "ask_user",
        "done",
    ]
    assert len(model.messages) == 4
    assert any(
        "multiple tool calls" in str(message.get("content"))
        for message in model.messages[1]
    )


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


def _authorized_calendar_permit() -> Any:
    from inbox2action.stage3.contracts import (
        ActionStatus,
        ApprovalRecord,
        ApprovalStatus,
        payload_hash,
    )
    from inbox2action.stage3.workflow import authorize_execution

    state = _calendar_permit()
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
    return authorize_execution(
        state.model_copy(
            update={
                "actions": [approved],
                "current_action_id": proposal.action_id,
            }
        ),
        proposal.action_id,
    )


def _realistic_event_response(permit: Any, *, event_id: str | None = None) -> dict[str, object]:
    return {
        "kind": "calendar#event",
        "id": event_id or permit.idempotency_key,
        "summary": "项目评审",
        "start": {"dateTime": B_START.isoformat(), "timeZone": "Asia/Shanghai"},
        "end": {"dateTime": B_END.isoformat(), "timeZone": "Asia/Shanghai"},
        "extendedProperties": {
            "private": {
                "i2a_k": permit.idempotency_key,
                "i2a_h": permit.approved_payload_hash,
                "i2a_a": permit.action_id,
            }
        },
    }


async def _no_sleep(_: float) -> None:
    return None


def _http_error(status: int, message: str = "provider failure") -> HttpError:
    return HttpError(
        FakeHttpResponse(status),
        json.dumps(
            {
                "error": {
                    "code": status,
                    "message": message,
                    "errors": [{"reason": "test_reason"}],
                }
            }
        ).encode(),
    )


@pytest.mark.asyncio
async def test_production_insert_accepts_realistic_event_and_sends_safe_body() -> None:
    permit = _authorized_calendar_permit()
    service = FakeGoogleCalendarService(_realistic_event_response(permit))
    executor = GoogleCalendarWriteExecutor(
        GoogleCalendarClient(service),
        calendar_id="trusted-calendar@example.com",
        enabled=True,
    )

    result = await executor.execute(permit)

    assert result.status == "succeeded"
    assert result.resource is not None
    assert result.resource.resource_id == permit.idempotency_key
    assert service.insert_kwargs is not None
    assert service.insert_kwargs["calendarId"] == "trusted-calendar@example.com"
    assert service.insert_kwargs["eventId"] == permit.idempotency_key
    assert service.insert_kwargs["sendUpdates"] == "none"
    assert "fields" not in service.insert_kwargs
    body = service.insert_kwargs["body"]
    assert isinstance(body, dict)
    assert body["id"] == permit.idempotency_key
    assert body["summary"] == "项目评审"
    assert body["description"] == "评审材料"
    assert body["start"] == {
        "dateTime": B_START.isoformat(),
        "timeZone": "Asia/Shanghai",
    }
    assert body["end"] == {
        "dateTime": B_END.isoformat(),
        "timeZone": "Asia/Shanghai",
    }
    assert body["extendedProperties"] == {
        "private": {
            "i2a_k": permit.idempotency_key,
            "i2a_h": permit.approved_payload_hash,
            "i2a_a": permit.action_id,
        }
    }
    assert "attendees" not in body
    assert "conferenceData" not in body
    assert result.diagnostics is not None
    assert result.diagnostics["insert_attempt"]["outcome_class"] == (
        InsertOutcomeClass.SUCCESS_RESPONSE.value
    )


def test_production_insert_missing_id_exposes_sanitized_response_diagnostics() -> None:
    service = FakeGoogleCalendarService({"kind": "calendar#event"})
    client = GoogleCalendarClient(service)

    with pytest.raises(GoogleCalendarInvalidResponseError) as raised:
        client.insert_event(
            calendar_id="trusted-calendar@example.com",
            event_id="deterministic-event-id",
            body={"id": "deterministic-event-id"},
        )

    diagnostics = raised.value.diagnostics
    assert isinstance(diagnostics, GoogleCalendarResponseDiagnostics)
    assert diagnostics.as_dict() == {
        "http_status": 200,
        "content_type": "application/json",
        "decoded_type": "dict",
        "top_level_keys": ("kind",),
        "has_id": False,
        "has_status": False,
        "has_htmlLink": False,
        "has_error": False,
    }


def test_production_insert_non_json_2xx_exposes_decoding_invariant() -> None:
    service = FakeGoogleCalendarService("<html>proxy response</html>")
    service.insert_request.http_response = FakeHttpResponse(200, "text/html")
    client = GoogleCalendarClient(service)

    with pytest.raises(GoogleCalendarInvalidResponseError) as raised:
        client.insert_event(
            calendar_id="trusted-calendar@example.com",
            event_id="deterministic-event-id",
            body={"id": "deterministic-event-id"},
        )

    diagnostics = raised.value.diagnostics
    assert isinstance(diagnostics, GoogleCalendarResponseDiagnostics)
    assert diagnostics.http_status == 200
    assert diagnostics.content_type == "text/html"
    assert diagnostics.decoded_type == "str"
    assert diagnostics.top_level_keys == ()
    assert diagnostics.has_id is False
    assert diagnostics.has_error is False
    assert raised.value.insert_diagnostic is not None
    assert raised.value.insert_diagnostic.outcome_class == (
        InsertOutcomeClass.INVALID_SUCCESS_RESPONSE
    )
    assert raised.value.insert_diagnostic.http_status == 200
    assert raised.value.insert_diagnostic.response_received is True


@pytest.mark.asyncio
async def test_returned_event_id_mismatch_fails_closed() -> None:
    permit = _authorized_calendar_permit()
    service = FakeGoogleCalendarService(
        _realistic_event_response(permit, event_id="another-event-id")
    )
    executor = GoogleCalendarWriteExecutor(
        GoogleCalendarClient(service),
        calendar_id="trusted-calendar@example.com",
        enabled=True,
    )

    result = await executor.execute(permit)

    assert result.status == "failed"
    assert result.error_code == "google_calendar_identity_mismatch"


def test_google_error_response_is_provider_error_with_safe_metadata() -> None:
    error = HttpError(
        FakeHttpResponse(400),
        b'{"error":{"code":400,"message":"invalid request"}}',
    )
    client = GoogleCalendarClient(
        FakeGoogleCalendarService(
            insert_error=error,
        )
    )

    with pytest.raises(GoogleCalendarApiError) as raised:
        client.insert_event(
            calendar_id="trusted-calendar@example.com",
            event_id="deterministic-event-id",
            body={"id": "deterministic-event-id"},
        )

    assert raised.value.status == 400
    diagnostics = raised.value.diagnostics
    assert isinstance(diagnostics, GoogleCalendarResponseDiagnostics)
    assert diagnostics.http_status == 400
    assert diagnostics.content_type == "application/json"
    assert diagnostics.decoded_type == "dict"
    assert diagnostics.top_level_keys == ("error",)
    assert diagnostics.has_error is True
    assert raised.value.insert_diagnostic is not None
    assert raised.value.insert_diagnostic.outcome_class == (
        InsertOutcomeClass.DEFINITIVE_HTTP_FAILURE
    )
    assert raised.value.insert_diagnostic.provider_reason == (
        "invalid request"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 401, 403])
async def test_http_insert_failures_are_retained_and_never_retried(status: int) -> None:
    permit = _authorized_calendar_permit()
    service = FakeGoogleCalendarService(insert_error=_http_error(status))
    executor = GoogleCalendarWriteExecutor(
        GoogleCalendarClient(service),
        calendar_id="trusted-calendar@example.com",
        enabled=True,
        sleeper=_no_sleep,
    )

    result = await executor.execute(permit)

    assert result.status == "failed"
    assert result.error_code == f"google_calendar_http_{status}"
    assert service.insert_count == 1
    assert service.get_count == 0
    assert result.diagnostics is not None
    insert = result.diagnostics["insert_attempt"]
    assert insert["outcome_class"] == InsertOutcomeClass.DEFINITIVE_HTTP_FAILURE.value
    assert insert["http_status"] == status
    assert insert["exception_type"] == "HttpError"
    assert insert["has_error"] is True
    assert insert["provider_reason"] == "test_reason: provider failure"


@pytest.mark.asyncio
async def test_409_diagnostic_and_bounded_reconciliation_are_separate() -> None:
    permit = _authorized_calendar_permit()
    service = FakeGoogleCalendarService(
        insert_error=_http_error(409, "already exists"),
        get_script=[
            _http_error(404, "not found yet"),
            _http_error(404, "still not found"),
            _realistic_event_response(permit),
        ],
    )
    executor = GoogleCalendarWriteExecutor(
        GoogleCalendarClient(service),
        calendar_id="trusted-calendar@example.com",
        enabled=True,
        sleeper=_no_sleep,
    )

    result = await executor.execute(permit)

    assert result.status == "succeeded"
    assert service.insert_count == 1
    assert service.get_count == 3
    assert result.diagnostics is not None
    assert result.diagnostics["insert_attempt"]["outcome_class"] == (
        InsertOutcomeClass.DUPLICATE_409.value
    )
    reconciliation = result.diagnostics["reconciliation"]
    assert reconciliation["get_attempt_count"] == 3
    assert [item["http_status"] for item in reconciliation["attempts"]] == [
        404,
        404,
        200,
    ]
    assert reconciliation["final_outcome"] == "found_identity_match"


@pytest.mark.asyncio
async def test_transport_timeout_reconciles_bounded_without_second_insert() -> None:
    permit = _authorized_calendar_permit()
    service = FakeGoogleCalendarService(
        insert_error=TimeoutError("socket timeout"),
        get_script=[
            _http_error(404),
            _http_error(404),
            _http_error(404),
        ],
    )
    executor = GoogleCalendarWriteExecutor(
        GoogleCalendarClient(service),
        calendar_id="trusted-calendar@example.com",
        enabled=True,
        sleeper=_no_sleep,
    )

    result = await executor.execute(permit)

    assert result.status == "unknown"
    assert result.error_code == "google_calendar_reconciliation_unresolved"
    assert service.insert_count == 1
    assert service.get_count == 3
    assert result.diagnostics is not None
    assert result.diagnostics["insert_attempt"]["outcome_class"] == (
        InsertOutcomeClass.AMBIGUOUS_TRANSPORT_FAILURE.value
    )
    assert result.diagnostics["insert_attempt"]["exception_type"] == "TimeoutError"
    reconciliation = result.diagnostics["reconciliation"]
    assert reconciliation["get_attempt_count"] == 3
    assert all(item["http_status"] == 404 for item in reconciliation["attempts"])
    assert reconciliation["final_outcome"] == "not_found"


@pytest.mark.asyncio
async def test_invalid_success_response_preserves_insert_diagnostic_through_reconcile() -> None:
    permit = _authorized_calendar_permit()
    service = FakeGoogleCalendarService(
        {"kind": "calendar#event"},
        get_script=[_http_error(404), _http_error(404), _http_error(404)],
    )
    executor = GoogleCalendarWriteExecutor(
        GoogleCalendarClient(service),
        calendar_id="trusted-calendar@example.com",
        enabled=True,
        sleeper=_no_sleep,
    )

    result = await executor.execute(permit)

    assert result.status == "unknown"
    assert service.insert_count == 1
    assert service.get_count == 3
    assert result.diagnostics is not None
    assert result.diagnostics["insert_attempt"]["outcome_class"] == (
        InsertOutcomeClass.INVALID_SUCCESS_RESPONSE.value
    )
    assert result.diagnostics["insert_attempt"]["http_status"] == 200
    assert result.diagnostics["reconciliation"]["final_outcome"] == "not_found"


def test_local_request_construction_failure_is_classified_without_response() -> None:
    service = FakeGoogleCalendarService(
        insert_construction_error=ValueError("client_secret=do-not-record")
    )
    client = GoogleCalendarClient(service)

    with pytest.raises(GoogleCalendarLocalClientError) as raised:
        client.insert_event(
            calendar_id="trusted-calendar@example.com",
            event_id="deterministic-event-id",
            body={"id": "deterministic-event-id"},
        )

    diagnostic = raised.value.insert_diagnostic
    assert diagnostic is not None
    assert diagnostic.outcome_class == InsertOutcomeClass.LOCAL_CLIENT_FAILURE
    assert diagnostic.exception_type == "ValueError"
    assert diagnostic.response_received is False
    assert diagnostic.request_may_have_reached_server is False
    assert "do-not-record" not in (diagnostic.provider_reason or "")


@pytest.mark.asyncio
async def test_timeout_404_404_found_reconciles_with_identity_match() -> None:
    permit = _authorized_calendar_permit()
    service = FakeGoogleCalendarService(
        insert_error=TimeoutError("socket timeout"),
        get_script=[
            _http_error(404),
            _http_error(404),
            _realistic_event_response(permit),
        ],
    )
    executor = GoogleCalendarWriteExecutor(
        GoogleCalendarClient(service),
        calendar_id="trusted-calendar@example.com",
        enabled=True,
        sleeper=_no_sleep,
    )

    result = await executor.execute(permit)

    assert result.status == "succeeded"
    assert service.insert_count == 1
    assert result.diagnostics is not None
    assert result.diagnostics["reconciliation"]["final_outcome"] == (
        "found_identity_match"
    )


@pytest.mark.asyncio
async def test_reconciliation_identity_mismatch_fails_closed_without_retry() -> None:
    permit = _authorized_calendar_permit()
    service = FakeGoogleCalendarService(
        insert_error=_http_error(409),
        get_responses=[_realistic_event_response(permit, event_id="other-id")],
    )
    executor = GoogleCalendarWriteExecutor(
        GoogleCalendarClient(service),
        calendar_id="trusted-calendar@example.com",
        enabled=True,
        sleeper=_no_sleep,
    )

    result = await executor.execute(permit)

    assert result.status == "failed"
    assert result.error_code == "google_calendar_identity_mismatch"
    assert service.insert_count == 1
    assert service.get_count == 1
    assert result.diagnostics is not None
    assert result.diagnostics["reconciliation"]["final_outcome"] == (
        "found_identity_mismatch"
    )


@pytest.mark.asyncio
async def test_409_reconciles_same_id_without_second_insert() -> None:
    permit = _authorized_calendar_permit()
    error = HttpError(
        FakeHttpResponse(409),
        b'{"error":{"code":409,"message":"already exists"}}',
    )
    service = FakeGoogleCalendarService(
        insert_error=error,
        get_response=_realistic_event_response(permit),
    )
    executor = GoogleCalendarWriteExecutor(
        GoogleCalendarClient(service),
        calendar_id="trusted-calendar@example.com",
        enabled=True,
    )

    result = await executor.execute(permit)

    assert result.status == "succeeded"
    assert service.insert_kwargs is not None
    assert service.insert_kwargs["eventId"] == permit.idempotency_key
    assert service.get_kwargs == {
        "calendarId": "trusted-calendar@example.com",
        "eventId": permit.idempotency_key,
    }


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
