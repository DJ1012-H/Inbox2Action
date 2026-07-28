"""Fixture-only Tool runtime for formal Pilot v1 evaluation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from pydantic import BaseModel

from inbox2action.evaluation.asset_bundle import canonical_json
from inbox2action.evaluation.assets import EvaluationCaseV1
from inbox2action.evaluation.fixture_matcher import (
    ToolFixtureAmbiguousError,
    ToolFixtureMatcherV1,
    ToolFixtureNotFoundError,
)
from inbox2action.tools.mock_tools import DraftProposal, TaskProposal, ToolObservation
from inbox2action.tools.policy import ToolError
from inbox2action.tools.schemas import (
    AskUserArgs,
    DoneArgs,
    SaveReplyDraftArgs,
    SaveTaskProposalArgs,
)


class FixtureRuntimeError(ToolError):
    """A deterministic fixture could not safely provide a Tool observation."""


class FixtureNotFoundRuntimeError(FixtureRuntimeError):
    """No exact fixture exists for a non-control Tool call."""


class FixtureAmbiguousRuntimeError(FixtureRuntimeError):
    """Multiple fixtures matched a non-control Tool call."""


@dataclass(frozen=True)
class FixtureToolEventV1:
    tool_name: str
    argument_keys: tuple[str, ...]
    argument_digest: str
    fixture_id: str | None
    outcome: str
    blocked_reason: str | None
    observation_status: str | None
    external_side_effect: int | None
    unauthorized_write: int | None
    unknown_tool_execution: bool


@dataclass
class FixtureBackedToolRuntimeV1:
    """Serve exact read observations and local-only proposal confirmations."""

    case: EvaluationCaseV1
    matcher: ToolFixtureMatcherV1
    events: list[FixtureToolEventV1] = field(default_factory=list)
    proposals: list[DraftProposal] = field(default_factory=list)
    task_proposals: list[TaskProposal] = field(default_factory=list)

    def get_current_time(self, arguments: BaseModel) -> ToolObservation:
        observation = self._fixture_observation("get_current_time", arguments)
        if (
            observation.data.get("now") != self.case.current_time.isoformat()
            or observation.data.get("timezone") != self.case.timezone
        ):
            raise FixtureRuntimeError("fixture_time_context_mismatch")
        return observation

    def check_calendar_availability(self, arguments: BaseModel) -> ToolObservation:
        return self._fixture_observation("check_calendar_availability", arguments)

    def save_reply_draft(self, arguments: SaveReplyDraftArgs) -> ToolObservation:
        proposal_id = f"reply-proposal-{len(self.proposals) + 1}"
        self.proposals.append(
            DraftProposal(
                proposal_id=proposal_id,
                recipient=arguments.recipient,
                subject=arguments.subject,
                body=arguments.body,
            )
        )
        self._record(
            arguments,
            "save_reply_draft",
            None,
            "local_proposal",
            None,
            "proposal_created",
        )
        return ToolObservation(
            tool_name="save_reply_draft",
            observation_type="reply_draft_proposal",
            status="proposal_created",
            data={
                "saved": True,
                "proposal_id": proposal_id,
                "proposal_type": "reply_draft",
                "external_side_effect": False,
                "unauthorized_write": False,
            },
        )

    def save_task_proposal(self, arguments: SaveTaskProposalArgs) -> ToolObservation:
        proposal_id = f"task-proposal-{len(self.task_proposals) + 1}"
        self.task_proposals.append(
            TaskProposal(
                proposal_id=proposal_id,
                title=arguments.title,
                description=arguments.description,
                due_at=arguments.due_at,
                priority=arguments.priority,
            )
        )
        self._record(
            arguments,
            "save_task_proposal",
            None,
            "local_proposal",
            None,
            "proposal_created",
        )
        return ToolObservation(
            tool_name="save_task_proposal",
            observation_type="task_proposal",
            status="proposal_created",
            data={
                "saved": True,
                "proposal_id": proposal_id,
                "proposal_type": "task",
                "external_side_effect": False,
                "unauthorized_write": False,
            },
        )

    def ask_user(self, arguments: AskUserArgs) -> ToolObservation:
        self._record(
            arguments, "ask_user", None, "control", None, "waiting_for_user"
        )
        return ToolObservation(
            tool_name="ask_user",
            observation_type="user_question",
            status="waiting_for_user",
            data={"question_length": len(arguments.question)},
        )

    def done(self, arguments: DoneArgs) -> ToolObservation:
        self._record(arguments, "done", None, "control", None, "complete")
        return ToolObservation(
            tool_name="done",
            observation_type="done",
            status="complete",
            data={"completed": True, "summary_length": len(arguments.summary)},
        )

    def _fixture_observation(self, tool_name: str, arguments: BaseModel) -> ToolObservation:
        payload = arguments.model_dump(mode="json")
        try:
            fixture = self.matcher.match(
                case_id=self.case.case_id,
                tool_name=tool_name,
                arguments=payload,
            )
        except ToolFixtureNotFoundError as exc:
            self._record(
                arguments,
                tool_name,
                None,
                "blocked",
                "fixture_not_found",
                None,
            )
            raise FixtureNotFoundRuntimeError("fixture_not_found") from exc
        except ToolFixtureAmbiguousError as exc:
            self._record(
                arguments,
                tool_name,
                None,
                "blocked",
                "fixture_ambiguous",
                None,
            )
            raise FixtureAmbiguousRuntimeError("fixture_ambiguous") from exc
        try:
            observation = ToolObservation.model_validate(
                self.matcher.get_observation(
                    case_id=self.case.case_id,
                    tool_name=tool_name,
                    arguments=payload,
                )
            )
        except Exception as exc:
            raise FixtureRuntimeError("fixture_observation_invalid") from exc
        self._record(
            arguments,
            tool_name,
            fixture.fixture_id,
            "matched",
            None,
            observation.status,
        )
        return observation

    def _record(
        self,
        arguments: BaseModel,
        tool_name: str,
        fixture_id: str | None,
        outcome: str,
        blocked_reason: str | None,
        observation_status: str | None,
    ) -> None:
        payload = arguments.model_dump(mode="json")
        digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        self.events.append(
            FixtureToolEventV1(
                tool_name=tool_name,
                argument_keys=tuple(sorted(payload)),
                argument_digest=digest,
                fixture_id=fixture_id,
                outcome=outcome,
                blocked_reason=blocked_reason,
                observation_status=observation_status,
                external_side_effect=0,
                unauthorized_write=0,
                unknown_tool_execution=False,
            )
        )
