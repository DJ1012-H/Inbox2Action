from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class NoArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CheckCalendarAvailabilityArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    start: datetime
    end: datetime
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=64)

    @field_validator("start", "end")
    @classmethod
    def require_explicit_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must include an explicit timezone")
        return value

    @field_validator("timezone")
    @classmethod
    def require_known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a known IANA timezone") from exc
        return value

    @model_validator(mode="after")
    def validate_interval(self) -> CheckCalendarAvailabilityArgs:
        if self.end <= self.start:
            raise ValueError("end must be later than start")
        if self.end - self.start > timedelta(minutes=480):
            raise ValueError("meeting duration exceeds the safe limit")
        timezone = ZoneInfo(self.timezone)
        self.start = self.start.astimezone(timezone)
        self.end = self.end.astimezone(timezone)
        return self


class SaveReplyDraftArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    recipient: str | None = Field(default=None, max_length=320)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10000)


class SaveTaskProposalArgs(BaseModel):
    """Arguments for a local-only task proposal."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)
    due_at: datetime | None = None
    priority: Literal["low", "medium", "high"]

    @field_validator("due_at")
    @classmethod
    def require_explicit_offset(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("due_at must include an explicit UTC offset")
        return value


class CreateClickUpTaskArgs(SaveTaskProposalArgs):
    """Provider-neutral ClickUp task parameters for a later adapter."""


class CreateCalendarEventArgs(BaseModel):
    """Provider-neutral calendar event parameters for a later adapter."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    start: datetime
    end: datetime
    timezone: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=4000)
    attendees: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("start", "end")
    @classmethod
    def require_explicit_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must include an explicit timezone")
        return value

    @field_validator("timezone")
    @classmethod
    def require_known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a known IANA timezone") from exc
        return value

    @model_validator(mode="after")
    def validate_interval(self) -> CreateCalendarEventArgs:
        if self.end <= self.start:
            raise ValueError("end must be later than start")
        if self.end - self.start > timedelta(minutes=480):
            raise ValueError("event duration exceeds the safe limit")
        return self


class SaveCalendarProposalArgs(BaseModel):
    """Local-only, provider-neutral Calendar proposal parameters."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    summary: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    start_time: datetime
    end_time: datetime
    timezone: str = Field(
        default="Asia/Shanghai",
        min_length=1,
        max_length=64,
    )
    location: str | None = Field(default=None, max_length=1000)

    @field_validator("start_time", "end_time")
    @classmethod
    def require_explicit_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must include an explicit timezone")
        return value

    @field_validator("timezone")
    @classmethod
    def require_known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a known IANA timezone") from exc
        return value

    @model_validator(mode="after")
    def validate_interval(self) -> SaveCalendarProposalArgs:
        timezone = ZoneInfo(self.timezone)
        self.start_time = self.start_time.astimezone(timezone)
        self.end_time = self.end_time.astimezone(timezone)
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be later than start_time")
        if self.end_time - self.start_time > timedelta(minutes=480):
            raise ValueError("event duration exceeds the safe limit")
        return self


WRITE_ARGUMENT_MODELS: dict[str, type[BaseModel]] = {
    "save_reply_draft": SaveReplyDraftArgs,
    "save_task_proposal": SaveTaskProposalArgs,
    "create_clickup_task": CreateClickUpTaskArgs,
    "create_calendar_event": CreateCalendarEventArgs,
    "save_calendar_proposal": SaveCalendarProposalArgs,
}


def validate_write_tool_parameters(
    tool_name: str,
    parameters: Mapping[str, object],
) -> dict[str, object]:
    """Validate and normalize one Stage 3 write payload with its Tool schema."""

    argument_model = WRITE_ARGUMENT_MODELS.get(tool_name)
    if argument_model is None:
        raise ValueError("write Tool is not registered")
    validated = argument_model.model_validate(dict(parameters))
    return validated.model_dump(mode="json")


class AskUserArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=1000)


class DoneArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    summary: str = Field(min_length=1, max_length=1000)
