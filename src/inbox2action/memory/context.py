"""Validated, bounded context exposed to future workflow planners."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from inbox2action.memory.contracts import (
    CalendarPreferences,
    MemoryCategory,
    ReplyPreferences,
    TaskPreferences,
    TriagePreferences,
)


class PreferenceContext(BaseModel):
    """Safe planner input; it cannot contain credentials, bodies, or clients."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = 1
    triage: TriagePreferences = Field(default_factory=TriagePreferences)
    reply: ReplyPreferences = Field(default_factory=ReplyPreferences)
    task: TaskPreferences = Field(default_factory=TaskPreferences)
    calendar: CalendarPreferences = Field(default_factory=CalendarPreferences)
    versions: dict[MemoryCategory, int] = Field(default_factory=dict)

    def to_prompt_context(self) -> dict[str, Any]:
        """Serialize only non-empty preferences with an explicit soft-policy label."""

        values: dict[str, Any] = {
            "memory_role": "soft_preference_only",
            "triage_preferences": self.triage.model_dump(
                mode="json", exclude_none=True
            ),
            "reply_preferences": self.reply.model_dump(mode="json", exclude_none=True),
            "task_preferences": self.task.model_dump(mode="json", exclude_none=True),
            "calendar_preferences": self.calendar.model_dump(
                mode="json", exclude_none=True
            ),
        }
        return values
