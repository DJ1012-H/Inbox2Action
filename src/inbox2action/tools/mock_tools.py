from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from inbox2action.tools.schemas import (
    AskUserArgs,
    CheckCalendarAvailabilityArgs,
    DoneArgs,
    NoArguments,
    SaveCalendarProposalArgs,
    SaveReplyDraftArgs,
    SaveTaskProposalArgs,
)

ObservationStatus = Literal[
    "ok",
    "conflict",
    "proposal_created",
    "waiting_for_user",
    "complete",
]


class ToolObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    observation_type: str
    status: ObservationStatus
    data: dict[str, object] = Field(default_factory=dict)
    tool_call_id: str | None = None


@dataclass(frozen=True)
class DraftProposal:
    proposal_id: str
    recipient: str | None
    subject: str
    body: str


@dataclass(frozen=True)
class TaskProposal:
    proposal_id: str
    title: str
    description: str
    due_at: datetime | None
    priority: Literal["low", "medium", "high"]


@dataclass(frozen=True)
class CalendarProposal:
    proposal_id: str
    summary: str
    description: str | None
    start_time: datetime
    end_time: datetime
    timezone: str
    location: str | None


def _default_busy_intervals() -> list[tuple[datetime, datetime]]:
    timezone = ZoneInfo("Asia/Shanghai")
    return [
        (
            datetime(2026, 7, 27, 9, 0, tzinfo=timezone),
            datetime(2026, 7, 27, 10, 0, tzinfo=timezone),
        )
    ]


@dataclass
class MockToolRuntime:
    """In-memory deterministic runtime; it performs no file or network I/O."""

    now: datetime = field(
        default_factory=lambda: datetime(
            2026,
            7,
            26,
            9,
            0,
            tzinfo=ZoneInfo("Asia/Shanghai"),
        )
    )
    busy_intervals: list[tuple[datetime, datetime]] = field(
        default_factory=_default_busy_intervals
    )
    proposals: list[DraftProposal] = field(default_factory=list)
    task_proposals: list[TaskProposal] = field(default_factory=list)
    calendar_proposals: list[CalendarProposal] = field(default_factory=list)

    def get_current_time(self, _: NoArguments) -> ToolObservation:
        return ToolObservation(
            tool_name="get_current_time",
            observation_type="current_time",
            status="ok",
            data={"now": self.now.isoformat(), "timezone": "Asia/Shanghai"},
        )

    def check_calendar_availability(
        self,
        arguments: CheckCalendarAvailabilityArgs,
    ) -> ToolObservation:
        conflict = any(
            arguments.start < busy_end and arguments.end > busy_start
            for busy_start, busy_end in self.busy_intervals
        )
        if conflict:
            suggested_start = arguments.end + timedelta(minutes=30)
            return ToolObservation(
                tool_name="check_calendar_availability",
                observation_type="calendar_availability",
                status="conflict",
                data={
                    "available": False,
                    "conflict": True,
                    "suggested_start": suggested_start.isoformat(),
                    "timezone": arguments.timezone,
                },
            )
        return ToolObservation(
            tool_name="check_calendar_availability",
            observation_type="calendar_availability",
            status="ok",
            data={"available": True, "conflict": False, "timezone": arguments.timezone},
        )

    def save_reply_draft(self, arguments: SaveReplyDraftArgs) -> ToolObservation:
        proposal_id = f"proposal-{len(self.proposals) + 1}"
        self.proposals.append(
            DraftProposal(
                proposal_id=proposal_id,
                recipient=arguments.recipient,
                subject=arguments.subject,
                body=arguments.body,
            )
        )
        return ToolObservation(
            tool_name="save_reply_draft",
            observation_type="reply_draft_proposal",
            status="proposal_created",
            data={
                "proposal_id": proposal_id,
                "external_side_effects": 0,
                "subject_length": len(arguments.subject),
                "body_length": len(arguments.body),
            },
        )

    def save_calendar_proposal(
        self, arguments: SaveCalendarProposalArgs
    ) -> ToolObservation:
        """Store a local proposal; this method never calls a provider."""

        proposal_id = f"calendar-proposal-{len(self.calendar_proposals) + 1}"
        self.calendar_proposals.append(
            CalendarProposal(
                proposal_id=proposal_id,
                summary=arguments.summary,
                description=arguments.description,
                start_time=arguments.start_time,
                end_time=arguments.end_time,
                timezone=arguments.timezone,
                location=arguments.location,
            )
        )
        return ToolObservation(
            tool_name="save_calendar_proposal",
            observation_type="calendar_proposal",
            status="proposal_created",
            data={
                "proposal_id": proposal_id,
                "proposal_type": "calendar",
                "saved": True,
                "external_side_effect": False,
                "summary_length": len(arguments.summary),
                "description_length": len(arguments.description or ""),
                "timezone": arguments.timezone,
                "location_present": arguments.location is not None,
            },
        )

    def save_task_proposal(self, arguments: SaveTaskProposalArgs) -> ToolObservation:
        """Store a deterministic in-memory proposal without external task creation."""

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
        return ToolObservation(
            tool_name="save_task_proposal",
            observation_type="task_proposal",
            status="proposal_created",
            data={
                "proposal_id": proposal_id,
                "proposal_type": "task",
                "saved": True,
                "external_side_effect": False,
                "title_length": len(arguments.title),
                "description_length": len(arguments.description),
                "due_at_present": arguments.due_at is not None,
                "priority": arguments.priority,
            },
        )

    def ask_user(self, arguments: AskUserArgs) -> ToolObservation:
        return ToolObservation(
            tool_name="ask_user",
            observation_type="user_question",
            status="waiting_for_user",
            data={"question": arguments.question},
        )

    def done(self, arguments: DoneArgs) -> ToolObservation:
        return ToolObservation(
            tool_name="done",
            observation_type="done",
            status="complete",
            data={"completed": True, "summary_length": len(arguments.summary)},
        )
