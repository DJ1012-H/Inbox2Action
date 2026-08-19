from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from pydantic import ValidationError

from inbox2action.clickup import (
    ClickUpClient,
    ClickUpConfigurationError,
    ClickUpWriteExecutor,
)
from inbox2action.evaluation.policy_v3 import (
    ActionNodeV3,
    ActionPlanV3,
    ParameterResolutionStatus,
    ParameterResolutionV3,
)
from inbox2action.evaluation.triage_v3 import TriageResultV3
from inbox2action.llm.models import TriageDecision
from inbox2action.stage3 import (
    ActionProposal,
    ActionStatus,
    ApprovalError,
    ApprovalRecord,
    EmailEnvelope,
    ExecutionClaimOutcome,
    ExecutionResult,
    ExecutionStartOutcome,
    ExternalResourceRef,
    InMemoryExecutionLedger,
    Stage2PlanningBundle,
    Stage3WorkflowStatus,
    WorkflowAction,
    build_email_action_graph,
    prepare_workflow_state,
    workflow_state_to_graph,
)
from inbox2action.stage3.contracts import ApprovalStatus
from inbox2action.stage3.workflow import authorize_execution, payload_hash
from inbox2action.stage4.persistence import (
    _execution_result_from_row,
    _validate_binding,
    execution_ledger_table,
)


@dataclass
class FakeResponse:
    body: bytes
    status: int = 201
    closed: bool = False

    def read(self, amount: int = 0) -> bytes:
        assert amount == 1_048_577
        return self.body

    def close(self) -> None:
        self.closed = True


def _response(payload: object, *, status: int = 201) -> FakeResponse:
    return FakeResponse(json.dumps(payload).encode("utf-8"), status=status)


def _client(
    response: FakeResponse | Exception,
    *,
    field_payload: object | None = None,
    reconciliation: list[FakeResponse | Exception] | None = None,
) -> tuple[ClickUpClient, list[Any]]:
    calls: list[Any] = []
    field_response = _response(
        field_payload
        if field_payload is not None
        else {
            "fields": [
                {"id": "field-123", "name": "Inbox2Action Key", "type": "text"}
            ]
        },
        status=200,
    )
    reconciliation_responses = list(reconciliation or [])

    def execute(request: Any, timeout: float) -> FakeResponse:
        calls.append((request, timeout))
        if request.full_url.endswith("/field"):
            return field_response
        if request.method == "POST":
            if isinstance(response, Exception):
                raise response
            return response
        if reconciliation_responses:
            next_response = reconciliation_responses.pop(0)
            if isinstance(next_response, Exception):
                raise next_response
            return next_response
        return _response({"tasks": []}, status=200)

    return (
        ClickUpClient(
            "cu-test-secret",
            "123456",
            timeout_seconds=8,
            request_executor=execute,
        ),
        calls,
    )


async def _no_sleep(_: float) -> None:
    return None


def _task_state(*, tool_name: str = "save_task_proposal"):
    action_node = ActionNodeV3(
        action_id="task-1",
        tool_name=tool_name,  # type: ignore[arg-type]
        required_parameters=("title", "description", "priority"),
        parameter_resolutions=tuple(
            ParameterResolutionV3(
                field_name=field,
                status=ParameterResolutionStatus.RESOLVED,
                source="reviewed_stage7",
            )
            for field in ("title", "description", "priority")
        ),
        requires_approval=True,
    )
    proposal = ActionProposal(
        action_id="task-1",
        tool_name=tool_name,  # type: ignore[arg-type]
        parameters={
            "title": "Approved task",
            "description": "Created only after approval and ledger claim.",
            "due_at": "2026-08-20T10:00:00+08:00",
            "priority": "medium",
        },
    )
    return prepare_workflow_state(
        EmailEnvelope(
            account_id="stage7-account",
            message_id="stage7-message",
            from_address="sender@example.test",
            subject="Task request",
            body="Please create the reviewed task.",
        ),
        Stage2PlanningBundle(
            triage=TriageResultV3(
                decision=TriageDecision.ACTION_REQUIRED,
                reason="reviewed task request",
                confidence=1.0,
                suspected_prompt_injection=False,
                security_reason=None,
                safe_to_plan_actions=True,
            ),
            action_plan=ActionPlanV3(actions=(action_node,)),
            proposals=[proposal],
        ),
    )


def _approved_task_state(*, tool_name: str = "save_task_proposal"):
    state = _task_state(tool_name=tool_name)
    proposal = state.actions[0].proposal
    digest = payload_hash(proposal)
    return state.model_copy(
        update={
            "status": Stage3WorkflowStatus.APPROVED,
            "current_action_id": proposal.action_id,
            "actions": [
                WorkflowAction(
                    proposal=proposal,
                    status=ActionStatus.APPROVED,
                    approval=ApprovalRecord(
                        action_id=proposal.action_id,
                        revision=1,
                        status=ApprovalStatus.APPROVED,
                        payload_hash=digest,
                        approved_payload_hash=digest,
                    ),
                )
            ],
        }
    )


def test_external_resource_ref_and_execution_result_are_provider_neutral() -> None:
    resource = ExternalResourceRef(
        provider="clickup",
        resource_type="task",
        resource_id="task-123",
        url="https://app.clickup.com/t/task-123",
    )
    result = ExecutionResult(status="succeeded", resource=resource)

    assert result.resource == resource
    with pytest.raises(ValidationError):
        ExecutionResult(status="unknown", resource=resource)
    with pytest.raises(ValidationError):
        ExternalResourceRef(
            provider="clickup",
            resource_type="task",
            resource_id="task-123",
            url="http://app.clickup.com/t/task-123",
        )
    with pytest.raises(ValidationError):
        ExternalResourceRef(
            provider="clickup",
            resource_type="task",
            resource_id="",
            url=None,
        )


def test_create_task_maps_proposal_fields_and_returns_minimal_reference() -> None:
    client, calls = _client(
        _response(
            {
                "id": "task-123",
                "url": "https://app.clickup.com/t/task-123",
                "description": "provider payload is not propagated",
            }
        )
    )
    client.resolve_idempotency_field()

    created = client.create_task(
        title="Approved task",
        description="Task description",
        due_at="2026-08-20T10:00:00+08:00",
        priority="medium",
        idempotency_key="stable-key-123",
    )

    request, timeout = calls[-1]
    body = json.loads(request.data.decode("utf-8"))
    expected_due = int(datetime.fromisoformat("2026-08-20T10:00:00+08:00").timestamp() * 1000)
    assert created.task_id == "task-123"
    assert created.url == "https://app.clickup.com/t/task-123"
    assert request.method == "POST"
    assert request.full_url == "https://api.clickup.com/api/v2/list/123456/task"
    assert body == {
        "name": "Approved task",
        "description": "Task description",
        "priority": 3,
        "due_date": expected_due,
        "custom_fields": [{"id": "field-123", "value": "stable-key-123"}],
    }
    assert request.get_header("Authorization") == "cu-test-secret"
    assert timeout == 8


@pytest.mark.parametrize(
    ("priority", "clickup_priority"),
    [("low", 4), ("medium", 3), ("high", 2)],
)
def test_create_task_maps_all_priority_values(
    priority: str, clickup_priority: int
) -> None:
    client, calls = _client(_response({"id": "task-123"}))
    client.resolve_idempotency_field()

    client.create_task(
        title="Task",
        description="Description",
        due_at=None,
        priority=priority,
        idempotency_key="stable-key-123",
    )

    body = json.loads(calls[-1][0].data.decode("utf-8"))
    assert body == {
        "name": "Task",
        "description": "Description",
        "priority": clickup_priority,
        "custom_fields": [{"id": "field-123", "value": "stable-key-123"}],
    }


def test_idempotency_field_must_be_unique_and_text_typed() -> None:
    missing_client, missing_calls = _client(
        _response({"id": "must-not-be-created"}),
        field_payload={"fields": []},
    )
    with pytest.raises(ClickUpConfigurationError):
        missing_client.resolve_idempotency_field()

    duplicate_client, _ = _client(
        _response({"id": "must-not-be-created"}),
        field_payload={
            "fields": [
                {"id": "field-1", "name": "Inbox2Action Key", "type": "text"},
                {"id": "field-2", "name": "Inbox2Action Key", "type": "text"},
            ]
        },
    )
    with pytest.raises(ClickUpConfigurationError):
        duplicate_client.resolve_idempotency_field()

    wrong_type_client, _ = _client(
        _response({"id": "must-not-be-created"}),
        field_payload={
            "fields": [
                {"id": "field-1", "name": "Inbox2Action Key", "type": "drop_down"}
            ]
        },
    )
    with pytest.raises(ClickUpConfigurationError):
        wrong_type_client.resolve_idempotency_field()
    assert missing_calls and all(call[0].method == "GET" for call in missing_calls)


@pytest.mark.parametrize(
    ("status", "expected_status", "expected_code"),
    [
        (400, "failed", "clickup_invalid_request"),
        (401, "failed", "clickup_authentication"),
        (403, "failed", "clickup_forbidden"),
        (404, "failed", "clickup_not_found"),
        (429, "failed", "clickup_rate_limited"),
        (500, "unknown", "clickup_reconciliation_unresolved"),
        (503, "unknown", "clickup_reconciliation_unresolved"),
    ],
)
@pytest.mark.asyncio
async def test_provider_errors_are_safe_and_never_retried(
    status: int,
    expected_status: str,
    expected_code: str,
) -> None:
    client, calls = _client(_response({"error": "not propagated"}, status=status))
    result = await ClickUpWriteExecutor(client, enabled=True).execute(
        authorize_execution(_approved_task_state(), "task-1")
    )

    assert result.status == expected_status
    assert result.error_code == expected_code
    assert result.resource is None
    assert len(calls) == (5 if status >= 500 else 2)


@pytest.mark.asyncio
async def test_timeout_transport_and_invalid_success_response_are_unknown() -> None:
    timeout_client, timeout_calls = _client(TimeoutError())
    permit = authorize_execution(_approved_task_state(), "task-1")
    timeout_result = await ClickUpWriteExecutor(
        timeout_client, enabled=True
    ).execute(permit)

    invalid_client, invalid_calls = _client(FakeResponse(b"not-json", status=201))
    invalid_result = await ClickUpWriteExecutor(
        invalid_client, enabled=True
    ).execute(permit)

    assert timeout_result == ExecutionResult(
        status="unknown", error_code="clickup_reconciliation_unresolved"
    )
    assert invalid_result == ExecutionResult(
        status="unknown", error_code="clickup_reconciliation_unresolved"
    )
    assert len(timeout_calls) == 5
    assert len(invalid_calls) == 5


@pytest.mark.asyncio
async def test_ambiguous_post_reconciles_exact_match_without_post_replay() -> None:
    client, calls = _client(
        TimeoutError(),
        reconciliation=[
            _response(
                {
                    "tasks": [
                        {
                            "id": "task-created-before-timeout",
                            "name": "Approved task",
                            "url": "https://app.clickup.com/t/task-created-before-timeout",
                        }
                    ]
                },
                status=200,
            )
        ],
    )
    permit = authorize_execution(_approved_task_state(), "task-1")
    result = await ClickUpWriteExecutor(
        client,
        enabled=True,
        sleeper=lambda _: _no_sleep(),
    ).execute(permit)

    assert result.status == "succeeded"
    assert result.resource is not None
    assert result.resource.resource_id == "task-created-before-timeout"
    assert [call[0].method for call in calls] == ["GET", "POST", "GET"]
    query = parse_qs(urlsplit(calls[-1][0].full_url).query)
    assert json.loads(query["custom_fields"][0]) == [
        {
            "field_id": "field-123",
            "operator": "==",
            "value": permit.idempotency_key,
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tasks", "error_code"),
    [
        ([], "clickup_reconciliation_unresolved"),
        (
            [
                {"id": "task-a", "name": "A"},
                {"id": "task-b", "name": "B"},
            ],
            "clickup_reconciliation_conflict",
        ),
    ],
)
async def test_reconciliation_zero_or_multiple_matches_stays_unknown(
    tasks: list[dict[str, str]], error_code: str
) -> None:
    client, calls = _client(
        _response({"id": "created-but-unreadable"}, status=500),
        reconciliation=[_response({"tasks": tasks}, status=200)],
    )
    result = await ClickUpWriteExecutor(
        client,
        enabled=True,
        reconciliation_attempts=1,
    ).execute(authorize_execution(_approved_task_state(), "task-1"))

    assert result == ExecutionResult(status="unknown", error_code=error_code)
    assert sum(call[0].method == "POST" for call in calls) == 1


@pytest.mark.asyncio
async def test_missing_idempotency_field_fails_closed_before_post() -> None:
    client, calls = _client(
        _response({"id": "must-not-be-created"}),
        field_payload={"fields": []},
    )
    result = await ClickUpWriteExecutor(client, enabled=True).execute(
        authorize_execution(_approved_task_state(), "task-1")
    )

    assert result.status == "failed"
    assert result.error_code == "clickup_preflight_configuration"
    assert all(call[0].method == "GET" for call in calls)


def test_naive_due_at_fails_closed_before_post() -> None:
    client, calls = _client(_response({"id": "must-not-be-created"}))
    client.resolve_idempotency_field()
    with pytest.raises(ClickUpConfigurationError):
        client.create_task(
            title="Task",
            description="Description",
            due_at=datetime(2026, 8, 20, 10, 0, tzinfo=UTC).replace(tzinfo=None),
            priority="medium",
            idempotency_key="stable-key-123",
        )
    assert [call[0].method for call in calls] == ["GET"]


@pytest.mark.asyncio
async def test_disabled_missing_config_and_unsupported_tool_make_zero_http_calls() -> None:
    client, calls = _client(_response({"id": "must-not-be-created"}))
    permit = authorize_execution(_approved_task_state(), "task-1")

    disabled = await ClickUpWriteExecutor(client, enabled=False).execute(permit)
    missing = await ClickUpWriteExecutor(None, enabled=True).execute(permit)
    unsupported_permit = authorize_execution(
        _approved_task_state(tool_name="create_clickup_task"), "task-1"
    )
    unsupported = await ClickUpWriteExecutor(client, enabled=True).execute(
        unsupported_permit
    )

    assert [result.error_code for result in (disabled, missing, unsupported)] == [
        "clickup_disabled",
        "clickup_configuration",
        "clickup_unsupported_tool",
    ]
    assert all(result.status == "failed" for result in (disabled, missing, unsupported))
    assert calls == []


@pytest.mark.asyncio
async def test_graph_does_not_post_before_approval_or_after_rejection() -> None:
    client, calls = _client(_response({"id": "must-not-be-created"}))
    graph = build_email_action_graph(
        checkpointer=InMemorySaver(),
        execution_ledger=InMemoryExecutionLedger(),
        write_executor=ClickUpWriteExecutor(client, enabled=True),
    )
    config = {"configurable": {"thread_id": _task_state().thread_id}}

    interrupted = await graph.ainvoke(
        workflow_state_to_graph(_task_state()), config
    )
    assert interrupted["__interrupt__"][0].value["kind"] == "approval_required"
    assert calls == []

    rejected = await graph.ainvoke(
        Command(resume={"decision": "reject", "expected_revision": 1}),
        config,
    )
    assert rejected["status"] == "rejected"
    assert calls == []


@pytest.mark.asyncio
async def test_stale_approval_does_not_post() -> None:
    client, calls = _client(_response({"id": "must-not-be-created"}))
    graph = build_email_action_graph(
        checkpointer=InMemorySaver(),
        execution_ledger=InMemoryExecutionLedger(),
        write_executor=ClickUpWriteExecutor(client, enabled=True),
    )
    state = _task_state()
    config = {"configurable": {"thread_id": state.thread_id}}
    await graph.ainvoke(workflow_state_to_graph(state), config)

    with pytest.raises(ApprovalError):
        await graph.ainvoke(
            Command(resume={"decision": "approve", "expected_revision": 2}),
            config,
        )
    assert calls == []


@pytest.mark.asyncio
async def test_approved_graph_posts_once_and_stores_resource_in_state() -> None:
    client, calls = _client(
        _response({"id": "task-123", "url": "https://app.clickup.com/t/task-123"})
    )
    graph = build_email_action_graph(
        checkpointer=InMemorySaver(),
        execution_ledger=InMemoryExecutionLedger(),
        write_executor=ClickUpWriteExecutor(client, enabled=True),
    )
    state = _task_state()
    config = {"configurable": {"thread_id": state.thread_id}}
    await graph.ainvoke(workflow_state_to_graph(state), config)

    completed = await graph.ainvoke(
        Command(resume={"decision": "approve", "expected_revision": 1}),
        config,
    )

    assert completed["status"] == "completed"
    assert len(calls) == 2
    assert completed["actions"][0]["result"] == {
        "status": "succeeded",
        "error_code": None,
        "resource": {
            "provider": "clickup",
            "resource_type": "task",
            "resource_id": "task-123",
            "url": "https://app.clickup.com/t/task-123",
        },
    }


@pytest.mark.asyncio
async def test_duplicate_and_restart_recover_the_same_resource_without_post() -> None:
    original_state = _approved_task_state()
    permit = authorize_execution(original_state, "task-1")
    resource = ExternalResourceRef(
        provider="clickup",
        resource_type="task",
        resource_id="task-123",
        url="https://app.clickup.com/t/task-123",
    )
    stored = ExecutionResult(status="succeeded", resource=resource)
    ledger = InMemoryExecutionLedger()
    assert await ledger.claim(permit) is ExecutionClaimOutcome.CLAIMED
    assert await ledger.begin_execution(permit) is ExecutionStartOutcome.STARTED
    await ledger.complete(permit, stored)
    assert await ledger.claim(permit) is ExecutionClaimOutcome.ALREADY_SUCCEEDED
    assert await ledger.get_result(permit) == stored

    client, calls = _client(_response({"id": "must-not-be-created"}))
    recovering_state = original_state.model_copy(
        update={
            "status": Stage3WorkflowStatus.EXECUTION_CLAIMED,
            "actions": [
                original_state.actions[0].model_copy(
                    update={"status": ActionStatus.EXECUTION_CLAIMED}
                )
            ],
        }
    )
    graph = build_email_action_graph(
        checkpointer=InMemorySaver(),
        execution_ledger=ledger,
        write_executor=ClickUpWriteExecutor(client, enabled=True),
    )
    result = await graph.ainvoke(
        workflow_state_to_graph(recovering_state),
        {"configurable": {"thread_id": recovering_state.thread_id}},
    )

    assert result["status"] == "completed"
    assert result["actions"][0]["result"]["resource"] == {
        "provider": "clickup",
        "resource_type": "task",
        "resource_id": "task-123",
        "url": "https://app.clickup.com/t/task-123",
    }
    assert calls == []


@pytest.mark.asyncio
async def test_unknown_restart_uses_get_only_reconciliation_and_durable_transition() -> None:
    original_state = _approved_task_state()
    permit = authorize_execution(original_state, "task-1")
    ledger = InMemoryExecutionLedger()
    await ledger.claim(permit)
    await ledger.begin_execution(permit)
    await ledger.complete(
        permit,
        ExecutionResult(status="unknown", error_code="clickup_transport_ambiguous"),
    )
    unknown_state = original_state.model_copy(
        update={
            "status": Stage3WorkflowStatus.UNKNOWN,
            "current_action_id": "task-1",
            "actions": [
                original_state.actions[0].model_copy(
                    update={
                        "status": ActionStatus.UNKNOWN,
                        "error_code": "clickup_transport_ambiguous",
                        "result": ExecutionResult(
                            status="unknown",
                            error_code="clickup_transport_ambiguous",
                        ),
                    }
                )
            ],
        }
    )
    client, calls = _client(
        _response({"id": "must-not-be-created"}),
        reconciliation=[
            _response(
                {
                    "tasks": [
                        {
                            "id": "recovered-task",
                            "name": "Approved task",
                            "url": "https://app.clickup.com/t/recovered-task",
                        }
                    ]
                },
                status=200,
            )
        ],
    )
    graph = build_email_action_graph(
        checkpointer=InMemorySaver(),
        execution_ledger=ledger,
        write_executor=ClickUpWriteExecutor(
            client,
            enabled=True,
            sleeper=_no_sleep,
            reconciliation_attempts=1,
        ),
    )

    recovered = await graph.ainvoke(
        workflow_state_to_graph(unknown_state),
        {"configurable": {"thread_id": unknown_state.thread_id}},
    )

    assert recovered["status"] == "completed"
    assert [call[0].method for call in calls] == ["GET", "GET"]
    assert recovered["actions"][0]["result"]["resource"]["resource_id"] == (
        "recovered-task"
    )
    assert (
        await ledger.get_result(permit)
    ) == ExecutionResult(
        status="succeeded",
        resource=ExternalResourceRef(
            provider="clickup",
            resource_type="task",
            resource_id="recovered-task",
            url="https://app.clickup.com/t/recovered-task",
        ),
    )


@pytest.mark.asyncio
async def test_reconcile_success_rejects_non_unknown_or_missing_resource() -> None:
    state = _approved_task_state()
    permit = authorize_execution(state, "task-1")
    ledger = InMemoryExecutionLedger()
    await ledger.claim(permit)
    await ledger.begin_execution(permit)
    with pytest.raises(RuntimeError, match="succeeded resource"):
        await ledger.reconcile_success(
            permit, ExecutionResult(status="unknown", error_code="not-ready")
        )
    await ledger.complete(
        permit,
        ExecutionResult(status="succeeded", resource=ExternalResourceRef(
            provider="clickup", resource_type="task", resource_id="task-1"
        )),
    )
    with pytest.raises(RuntimeError, match="not eligible"):
        await ledger.reconcile_success(
            permit,
            ExecutionResult(status="succeeded", resource=ExternalResourceRef(
                provider="clickup", resource_type="task", resource_id="task-2"
            )),
        )


@pytest.mark.asyncio
async def test_inmemory_ledger_rejects_wrong_binding_for_result_recovery() -> None:
    state = _approved_task_state()
    permit = authorize_execution(state, "task-1")
    ledger = InMemoryExecutionLedger()
    await ledger.claim(permit)
    await ledger.begin_execution(permit)
    await ledger.complete(
        permit,
        ExecutionResult(
            status="succeeded",
            resource=ExternalResourceRef(
                provider="clickup",
                resource_type="task",
                resource_id="task-123",
            ),
        ),
    )
    wrong = permit.model_copy(update={"action_id": "other-action"})

    with pytest.raises(RuntimeError, match="bound to another action"):
        await ledger.get_result(wrong)


def test_postgres_resource_helpers_and_metadata_preserve_legacy_nulls() -> None:
    columns = {column.name for column in execution_ledger_table.columns}
    assert {
        "resource_provider",
        "resource_type",
        "resource_id",
        "resource_url",
    }.issubset(columns)

    state = _approved_task_state()
    permit = authorize_execution(state, "task-1")
    row: dict[str, object] = {
        "thread_id": permit.thread_id,
        "action_id": permit.action_id,
        "payload_hash": permit.approved_payload_hash,
        "status": "succeeded",
        "error_code": None,
        "resource_provider": "clickup",
        "resource_type": "task",
        "resource_id": "task-123",
        "resource_url": None,
    }

    recovered = _execution_result_from_row(row)
    assert recovered.resource is not None
    assert recovered.resource.resource_id == "task-123"
    _validate_binding(row, permit)

    legacy = dict(row)
    legacy.update(
        {
            "status": "failed",
            "error_code": "clickup_invalid_request",
            "resource_provider": None,
            "resource_type": None,
            "resource_id": None,
            "resource_url": None,
        }
    )
    assert _execution_result_from_row(legacy) == ExecutionResult(
        status="failed", error_code="clickup_invalid_request"
    )


def test_stage7_resource_migration_is_forward_and_reversible() -> None:
    migration = Path(__file__).parents[2] / "db" / "alembic" / "versions" / "0004_stage7_execution_resources.py"
    source = migration.read_text(encoding="utf-8")

    assert 'revision: str = "0004_stage7_execution_resources"' in source
    assert 'down_revision: str | None = "0003_stage6_workflow_index"' in source
    for column in (
        "resource_provider",
        "resource_type",
        "resource_id",
        "resource_url",
    ):
        assert f'"{column}"' in source
    assert "def downgrade()" in source
