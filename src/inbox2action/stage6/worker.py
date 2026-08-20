from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from inbox2action.errors import ModelError
from inbox2action.gmail import GmailError, GmailReadonlyTransport
from inbox2action.stage3.contracts import (
    EmailEnvelope,
    Stage2PlanningBundle,
    WorkflowState,
    workflow_thread_id,
)
from inbox2action.stage3.graph import workflow_state_to_graph
from inbox2action.stage3.workflow import prepare_workflow_state
from inbox2action.stage6.index import WorkflowIndex
from inbox2action.stage6.ingestion import gmail_message_to_envelope
from inbox2action.stage6.planning import Stage6PlanningError


class Stage6Planner(Protocol):
    def plan(self, envelope: EmailEnvelope) -> Stage2PlanningBundle: ...


class EmailWorkflowGraph(Protocol):
    async def ainvoke(
        self, input: object, config: dict[str, object]
    ) -> dict[str, object]: ...

    async def aget_state(self, config: dict[str, object]) -> object: ...


@dataclass(frozen=True)
class PollResult:
    message_id: str
    thread_id: str
    status: str
    duplicate: bool = False
    error_code: str | None = None


class GmailWorkflowWorker:
    """Bounded polling worker that feeds the existing single EmailActionAgent."""

    def __init__(
        self,
        transport: GmailReadonlyTransport,
        planner: Stage6Planner,
        graph: EmailWorkflowGraph,
        index: WorkflowIndex,
    ) -> None:
        self._transport = transport
        self._planner = planner
        self._graph = graph
        self._index = index

    async def poll_once(self, *, max_messages: int = 10) -> list[PollResult]:
        profile = self._transport.get_profile()
        account_id = profile.email_address
        results: list[PollResult] = []
        for summary in self._transport.read_recent_messages(max_messages):
            thread_id = workflow_thread_id(account_id, summary.message_id)
            reserved = await self._index.reserve(
                thread_id=thread_id,
                account_id=account_id,
                message_id=summary.message_id,
                from_address=summary.from_address or None,
                subject=summary.subject,
                received_at=summary.date or None,
            )
            if not reserved:
                recovered = await self._recover_duplicate(summary.message_id, thread_id)
                if recovered is not None:
                    results.append(recovered)
                    continue
                results.append(
                    PollResult(
                        message_id=summary.message_id,
                        thread_id=thread_id,
                        status="duplicate",
                        duplicate=True,
                    )
                )
                continue

            try:
                message = self._transport.read_message(
                    summary.message_id,
                    thread_id=summary.thread_id,
                )
                envelope = gmail_message_to_envelope(message, account_id=account_id)
                plan_with_memory = getattr(self._planner, "plan_with_memory", None)
                if callable(plan_with_memory):
                    planning = await plan_with_memory(envelope)
                else:
                    planning = self._planner.plan(envelope)
                state = prepare_workflow_state(envelope, planning)
                output = await self._graph.ainvoke(
                    workflow_state_to_graph(state),
                    {"configurable": {"thread_id": state.thread_id}},
                )
                status = _graph_status(output)
                await self._index.set_status(thread_id, status)
                results.append(
                    PollResult(
                        message_id=summary.message_id,
                        thread_id=thread_id,
                        status=status,
                    )
                )
            except GmailError as exc:
                await self._index.set_status(thread_id, "failed")
                results.append(
                    PollResult(
                        message_id=summary.message_id,
                        thread_id=thread_id,
                        status="failed",
                        error_code=exc.code,
                    )
                )
            except ModelError:
                await self._index.set_status(thread_id, "failed")
                results.append(
                    PollResult(
                        message_id=summary.message_id,
                        thread_id=thread_id,
                        status="failed",
                        error_code="model_failed",
                    )
                )
            except Stage6PlanningError:
                await self._index.set_status(thread_id, "failed")
                results.append(
                    PollResult(
                        message_id=summary.message_id,
                        thread_id=thread_id,
                        status="failed",
                        error_code="planning_blocked",
                    )
                )
            except Exception:  # noqa: BLE001 - worker errors are fail-closed
                await self._index.set_status(thread_id, "failed")
                results.append(
                    PollResult(
                        message_id=summary.message_id,
                        thread_id=thread_id,
                        status="failed",
                        error_code="workflow_failed",
                    )
                )
        return results

    async def _recover_duplicate(
        self, message_id: str, thread_id: str
    ) -> PollResult | None:
        """Repair the listing index after a crash between graph and index writes."""

        try:
            snapshot = await self._graph.aget_state(
                {"configurable": {"thread_id": thread_id}}
            )
            values = getattr(snapshot, "values", None)
            if not isinstance(values, dict) or not values:
                return None
            state = WorkflowState.model_validate(values)
            status = state.status.value
            await self._index.set_status(thread_id, status)
            return PollResult(
                message_id=message_id,
                thread_id=thread_id,
                status=status,
                duplicate=True,
            )
        except Exception:  # noqa: BLE001 - recovery must not reprocess a message
            return None


def _graph_status(output: dict[str, object]) -> str:
    if output.get("__interrupt__"):
        return "waiting_for_approval"
    value = output.get("status")
    return value if isinstance(value, str) else "unknown"
