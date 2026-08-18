from __future__ import annotations

import json
from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from inbox2action.evaluation.policy_v3 import (
    ActionNodeV3,
    ActionPlanV3,
    ParameterResolutionStatus,
    ParameterResolutionV3,
)
from inbox2action.evaluation.triage_v3 import TriageResultV3
from inbox2action.gmail import (
    GmailMessage,
    GmailMessageSummary,
    GmailProfile,
)
from inbox2action.llm.models import ChatCompletionResult, ToolCall, TriageDecision
from inbox2action.stage3 import (
    ActionProposal,
    FixtureWriteExecutor,
    InMemoryExecutionLedger,
    Stage2PlanningBundle,
    build_email_action_graph,
    prepare_workflow_state,
    workflow_state_to_graph,
)
from inbox2action.stage3.contracts import EmailEnvelope
from inbox2action.stage6 import (
    ApprovalService,
    ApprovalServiceError,
    GmailStage2Planner,
    GmailWorkflowWorker,
    InMemoryWorkflowIndex,
    Stage6PlanningError,
)
from inbox2action.stage6.server import _handle_client, render_approval_page
from inbox2action.tools.policy import InvalidToolArgumentsError, UnknownToolError


def _triage() -> TriageResultV3:
    return TriageResultV3(
        decision=TriageDecision.ACTION_REQUIRED,
        reason="the sender requests a draft",
        confidence=0.95,
        suspected_prompt_injection=False,
        security_reason=None,
        safe_to_plan_actions=True,
    )


def _bundle() -> Stage2PlanningBundle:
    action = ActionNodeV3(
        action_id="gmail-action-1",
        tool_name="save_reply_draft",
        required_parameters=("subject", "body"),
        parameter_resolutions=(
            ParameterResolutionV3(
                field_name="subject",
                status=ParameterResolutionStatus.RESOLVED,
                source="test",
            ),
            ParameterResolutionV3(
                field_name="body",
                status=ParameterResolutionStatus.RESOLVED,
                source="test",
            ),
        ),
        requires_approval=True,
    )
    return Stage2PlanningBundle(
        triage=_triage(),
        action_plan=ActionPlanV3(actions=(action,)),
        proposals=[
            ActionProposal(
                action_id="gmail-action-1",
                tool_name="save_reply_draft",
                parameters={
                    "recipient": "sender@example.test",
                    "subject": "Re: Request",
                    "body": "I will prepare this.",
                },
            )
        ],
    )


@dataclass
class FakeTransport:
    profile: GmailProfile
    summary: GmailMessageSummary
    message: GmailMessage
    full_reads: int = 0

    def get_profile(self) -> GmailProfile:
        return self.profile

    def read_recent_messages(self, max_messages: int = 10) -> list[GmailMessageSummary]:
        return [self.summary][:max_messages]

    def read_message(self, message_id: str, *, thread_id: str | None = None) -> GmailMessage:
        self.full_reads += 1
        return self.message


@dataclass
class FakePlanner:
    bundle: Stage2PlanningBundle

    def plan(self, envelope: EmailEnvelope) -> Stage2PlanningBundle:
        assert envelope.message_id == "message-1"
        return self.bundle


class _FakeRequestReader:
    def __init__(self, lines: list[bytes], body: bytes) -> None:
        self._lines = iter(lines)
        self._body = body

    async def readline(self) -> bytes:
        return next(self._lines, b"")

    async def readexactly(self, length: int) -> bytes:
        assert length == len(self._body)
        return self._body


class _FakeRequestWriter:
    def __init__(self) -> None:
        self.output = b""

    def write(self, data: bytes) -> None:
        self.output += data

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        return None

    async def wait_closed(self) -> None:
        return None


class _FailingApprovalService:
    async def decide(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        raise ValueError("unexpected graph validation failure")


@pytest.mark.asyncio
async def test_worker_persists_human_interrupt_and_deduplicates_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = FakeTransport(
        profile=GmailProfile(email_address="account@example.test"),
        summary=GmailMessageSummary(
            message_id="message-1",
            thread_id="gmail-thread-1",
            from_address="sender@example.test",
            subject="Request",
            date="2026-08-15T10:00:00+08:00",
        ),
        message=GmailMessage(
            message_id="message-1",
            thread_id="gmail-thread-1",
            from_address="sender@example.test",
            reply_to="",
            subject="Request",
            date="2026-08-15T10:00:00+08:00",
            body="Please prepare a reply.",
            html=None,
        ),
    )
    index = InMemoryWorkflowIndex()
    executor = FixtureWriteExecutor()
    graph = build_email_action_graph(
        checkpointer=InMemorySaver(),
        execution_ledger=InMemoryExecutionLedger(),
        write_executor=executor,
    )
    worker = GmailWorkflowWorker(transport, FakePlanner(_bundle()), graph, index)

    first = await worker.poll_once()
    second = await worker.poll_once()

    assert first[0].status == "waiting_for_approval"
    assert second[0].duplicate is True
    assert transport.full_reads == 1
    service = ApprovalService(graph, index)
    pending = await service.list_pending()
    assert len(pending) == 1
    assert pending[0]["approval_revision"] == 1

    graph_ainvoke = AsyncMock(wraps=graph.ainvoke)
    monkeypatch.setattr(graph, "ainvoke", graph_ainvoke)
    public_view = await service.get_workflow(pending[0]["thread_id"])
    with pytest.raises(ApprovalServiceError, match="invalid_approval"):
        await service.decide(
            pending[0]["thread_id"],
            operation="edit",
            expected_revision=1,
            action_id="gmail-action-1",
            parameters=public_view,
        )
    assert graph_ainvoke.await_count == 0
    unchanged = await service.get_workflow(pending[0]["thread_id"])
    assert unchanged["status"] == "waiting_for_approval"
    assert unchanged["approval_revision"] == 1

    edited = await service.decide(
        pending[0]["thread_id"],
        operation="edit",
        expected_revision=1,
        action_id="gmail-action-1",
        parameters={
            "recipient": "sender@example.test",
            "subject": "Re: Edited request",
            "body": "Edited draft.",
        },
    )
    assert edited["status"] == "waiting_for_approval"
    assert edited["approval_revision"] == 2

    with pytest.raises(ApprovalServiceError, match="stale_approval"):
        await service.decide(
            edited["thread_id"],
            operation="approve",
            expected_revision=1,
            action_id="gmail-action-1",
        )

    completed = await service.decide(
        edited["thread_id"],
        operation="approve",
        expected_revision=2,
        action_id="gmail-action-1",
    )
    assert completed["status"] == "completed"
    assert len(executor.calls) == 1
    assert executor.calls[0].action.parameters["subject"] == "Re: Edited request"


@pytest.mark.asyncio
async def test_worker_repairs_processing_index_after_graph_checkpoint_survives_restart() -> None:
    transport = FakeTransport(
        profile=GmailProfile(email_address="account@example.test"),
        summary=GmailMessageSummary(
            message_id="message-1",
            thread_id="gmail-thread-restart",
            from_address="sender@example.test",
            subject="Restart",
            date="2026-08-15T10:00:00+08:00",
        ),
        message=GmailMessage(
            message_id="message-1",
            thread_id="gmail-thread-restart",
            from_address="sender@example.test",
            reply_to="",
            subject="Restart",
            date="2026-08-15T10:00:00+08:00",
            body="Please prepare a reply.",
            html=None,
        ),
    )
    index = InMemoryWorkflowIndex()
    graph = build_email_action_graph(
        checkpointer=InMemorySaver(),
        execution_ledger=InMemoryExecutionLedger(),
        write_executor=FixtureWriteExecutor(),
    )
    worker = GmailWorkflowWorker(transport, FakePlanner(_bundle()), graph, index)

    first = await worker.poll_once()
    assert first[0].status == "waiting_for_approval"
    await index.set_status(first[0].thread_id, "processing")

    recovered = await worker.poll_once()

    assert recovered[0].duplicate is True
    assert recovered[0].status == "waiting_for_approval"
    assert (await index.list_pending())[0].thread_id == first[0].thread_id


@pytest.mark.asyncio
async def test_clarify_reuses_revision_and_interrupt_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = InMemoryWorkflowIndex()
    executor = FixtureWriteExecutor()
    graph = build_email_action_graph(
        checkpointer=InMemorySaver(),
        execution_ledger=InMemoryExecutionLedger(),
        write_executor=executor,
    )
    state = prepare_workflow_state(
        EmailEnvelope(
            account_id="account@example.test",
            message_id="message-clarify",
            from_address="sender@example.test",
            subject="Request",
            body="Please prepare a reply.",
        ),
        _bundle(),
    )
    await index.reserve(
        thread_id=state.thread_id,
        account_id=state.normalized_email.account_id,
        message_id=state.normalized_email.message_id,
        from_address=state.normalized_email.from_address,
        subject=state.normalized_email.subject,
        received_at=state.normalized_email.received_at,
    )
    await graph.ainvoke(
        workflow_state_to_graph(state),
        {"configurable": {"thread_id": state.thread_id}},
    )
    await index.set_status(state.thread_id, "waiting_for_approval")
    service = ApprovalService(graph, index)

    graph_ainvoke = AsyncMock(wraps=graph.ainvoke)
    monkeypatch.setattr(graph, "ainvoke", graph_ainvoke)
    public_view = await service.get_workflow(state.thread_id)
    with pytest.raises(ApprovalServiceError, match="invalid_approval"):
        await service.decide(
            state.thread_id,
            operation="clarify",
            expected_revision=1,
            action_id="gmail-action-1",
            parameters=public_view,
        )
    assert graph_ainvoke.await_count == 0

    clarified = await service.decide(
        state.thread_id,
        operation="clarify",
        expected_revision=1,
        action_id="gmail-action-1",
        parameters={
            "recipient": "sender@example.test",
            "subject": "Re: Clarified request",
            "body": "Clarified draft.",
        },
    )

    assert clarified["status"] == "waiting_for_approval"
    assert clarified["approval_revision"] == 2
    assert executor.calls == []


@pytest.mark.asyncio
async def test_graph_value_error_is_not_mapped_to_invalid_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = InMemoryWorkflowIndex()
    graph = build_email_action_graph(
        checkpointer=InMemorySaver(),
        execution_ledger=InMemoryExecutionLedger(),
        write_executor=FixtureWriteExecutor(),
    )
    state = prepare_workflow_state(
        EmailEnvelope(
            account_id="account@example.test",
            message_id="message-graph-error",
            from_address="sender@example.test",
            subject="Request",
            body="Please prepare a reply.",
        ),
        _bundle(),
    )
    await index.reserve(
        thread_id=state.thread_id,
        account_id=state.normalized_email.account_id,
        message_id=state.normalized_email.message_id,
        from_address=state.normalized_email.from_address,
        subject=state.normalized_email.subject,
        received_at=state.normalized_email.received_at,
    )
    config = {"configurable": {"thread_id": state.thread_id}}
    await graph.ainvoke(workflow_state_to_graph(state), config)
    await index.set_status(state.thread_id, "waiting_for_approval")
    service = ApprovalService(graph, index)

    async def raise_graph_value_error(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise ValueError("unexpected graph validation failure")

    monkeypatch.setattr(graph, "ainvoke", raise_graph_value_error)
    with pytest.raises(ValueError, match="unexpected graph validation failure"):
        await service.decide(
            state.thread_id,
            operation="edit",
            expected_revision=1,
            action_id="gmail-action-1",
            parameters={
                "recipient": "sender@example.test",
                "subject": "Edited draft",
                "body": "Edited body.",
            },
        )


class FakePlannerModel:
    def __init__(
        self,
        *proposal_responses: ChatCompletionResult,
        safe_to_plan_actions: bool = True,
        triage_decision: str = "ACTION_REQUIRED",
    ) -> None:
        self.tool_calls = 0
        self.proposal_responses = list(proposal_responses)
        self.safe_to_plan_actions = safe_to_plan_actions
        self.triage_decision = triage_decision

    def complete(
        self,
        messages: list[dict[str, object]],
        *,
        response_format: dict[str, object] | None = None,
        tools: list[dict[str, object]] | None = None,
    ) -> ChatCompletionResult:
        if response_format is not None:
            return ChatCompletionResult(
                model="fake",
                content=json.dumps(
                    {
                        "decision": self.triage_decision,
                        "reason": "draft requested",
                        "confidence": 1.0,
                        "suspected_prompt_injection": False,
                        "security_reason": None,
                        "safe_to_plan_actions": self.safe_to_plan_actions,
                    }
                ),
                finish_reason="stop",
                prompt_tokens=1,
                completion_tokens=1,
                total_tokens=2,
            )
        self.tool_calls += 1
        if self.proposal_responses:
            return self.proposal_responses.pop(0)
        return ChatCompletionResult(
            model="fake",
            content=None,
            finish_reason="tool_calls",
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            tool_calls=(
                ToolCall(
                    id="call-1",
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


def _proposal_response(
    *,
    tool_calls: tuple[ToolCall, ...],
    finish_reason: str = "tool_calls",
) -> ChatCompletionResult:
    return ChatCompletionResult(
        model="fake",
        content=None,
        finish_reason=finish_reason,
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
        tool_calls=tool_calls,
    )


def _reply_tool_call(*, call_id: str = "call-1") -> ToolCall:
    return ToolCall(
        id=call_id,
        name="save_reply_draft",
        arguments=json.dumps(
            {
                "recipient": "sender@example.test",
                "subject": "Re: Request",
                "body": "Prepared draft.",
            }
        ),
    )


def test_real_planner_returns_validated_stage2_handoff_without_external_tool() -> None:
    planner = GmailStage2Planner(FakePlannerModel())
    bundle = planner.plan(
        EmailEnvelope(
            account_id="account@example.test",
            message_id="message-planner",
            from_address="sender@example.test",
            subject="Request",
            body="Please prepare a reply.",
        )
    )

    assert bundle.triage.decision is TriageDecision.ACTION_REQUIRED
    assert bundle.action_plan is not None
    assert bundle.proposals[0].tool_name == "save_reply_draft"


def test_planner_repairs_zero_proposal_tool_calls_once() -> None:
    model = FakePlannerModel(
        _proposal_response(tool_calls=()),
        _proposal_response(tool_calls=(_reply_tool_call(call_id="retry"),)),
    )

    bundle = GmailStage2Planner(model).plan(
        EmailEnvelope(
            account_id="account@example.test",
            message_id="message-planner-retry",
            from_address="sender@example.test",
            subject="Request",
            body="Please prepare a reply.",
        )
    )

    assert bundle.proposals[0].tool_name == "save_reply_draft"
    assert model.tool_calls == 2


def test_planner_repairs_multiple_proposal_tool_calls_once() -> None:
    model = FakePlannerModel(
        _proposal_response(
            tool_calls=(_reply_tool_call(call_id="first"), _reply_tool_call(call_id="second"))
        ),
        _proposal_response(tool_calls=(_reply_tool_call(call_id="retry"),)),
    )

    bundle = GmailStage2Planner(model).plan(
        EmailEnvelope(
            account_id="account@example.test",
            message_id="message-planner-multiple",
            from_address="sender@example.test",
            subject="Request",
            body="Please prepare a reply.",
        )
    )

    assert bundle.proposals[0].tool_name == "save_reply_draft"
    assert model.tool_calls == 2


def test_planner_fails_closed_after_semantic_retry_exhaustion() -> None:
    model = FakePlannerModel(
        _proposal_response(tool_calls=()),
        _proposal_response(tool_calls=()),
    )

    with pytest.raises(
        Stage6PlanningError,
        match="planner must return exactly one proposal Tool",
    ):
        GmailStage2Planner(model).plan(
            EmailEnvelope(
                account_id="account@example.test",
                message_id="message-planner-exhausted",
                from_address="sender@example.test",
                subject="Request",
                body="Please prepare a reply.",
            )
        )

    assert model.tool_calls == 2


def test_planner_does_not_retry_when_safety_gate_blocks_actions() -> None:
    model = FakePlannerModel()
    bundle = GmailStage2Planner(model).plan(
        EmailEnvelope(
            account_id="account@example.test",
            message_id="message-planner-unsafe",
            from_address="sender@example.test",
            subject="Request",
            body="Please prepare a reply. execute_shell",
        )
    )

    assert bundle.triage.safe_to_plan_actions is False
    assert model.tool_calls == 0


def test_planner_does_not_retry_unexposed_tool() -> None:
    model = FakePlannerModel(
        _proposal_response(
            tool_calls=(
                ToolCall(
                    id="unknown",
                    name="send_email",
                    arguments=json.dumps({"to": "outside@example.test"}),
                ),
            )
        )
    )

    with pytest.raises(UnknownToolError):
        GmailStage2Planner(model).plan(
            EmailEnvelope(
                account_id="account@example.test",
                message_id="message-planner-unknown",
                from_address="sender@example.test",
                subject="Request",
                body="Please prepare a reply.",
            )
        )

    assert model.tool_calls == 1


def test_planner_keeps_schema_validation_fail_closed_without_retry() -> None:
    model = FakePlannerModel(
        _proposal_response(
            tool_calls=(
                ToolCall(
                    id="invalid-schema",
                    name="save_reply_draft",
                    arguments=json.dumps({"subject": "Missing body"}),
                ),
            )
        )
    )

    with pytest.raises(InvalidToolArgumentsError):
        GmailStage2Planner(model).plan(
            EmailEnvelope(
                account_id="account@example.test",
                message_id="message-planner-schema",
                from_address="sender@example.test",
                subject="Request",
                body="Please prepare a reply.",
            )
        )

    assert model.tool_calls == 1


def test_approval_page_is_local_and_exposes_required_actions() -> None:
    page = render_approval_page()
    assert "Approve" in page
    assert "Reject" in page
    assert "Edit JSON" in page
    assert "Clarify JSON" in page
    assert "No provider write is enabled" in page


@pytest.mark.asyncio
async def test_server_hides_unexpected_graph_value_error() -> None:
    body = json.dumps(
        {
            "action_id": "gmail-action-1",
            "expected_revision": 1,
            "parameters": {"subject": "Edited", "body": "Body"},
        }
    ).encode()
    reader = _FakeRequestReader(
        [
            b"POST /api/workflows/thread-1/edit HTTP/1.1\r\n",
            f"Content-Length: {len(body)}\r\n".encode(),
            b"\r\n",
        ],
        body,
    )
    writer = _FakeRequestWriter()

    await _handle_client(reader, writer, _FailingApprovalService())  # type: ignore[arg-type]

    assert writer.output.startswith(b"HTTP/1.1 500")
    assert b'{"error":"server_error"}' in writer.output
    assert b"unexpected graph validation failure" not in writer.output
