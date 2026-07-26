from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class NoArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CheckCalendarAvailabilityArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    start: datetime
    end: datetime
    timezone: str = Field(default="Asia/Taipei", min_length=1, max_length=64)

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
        return self


class SaveReplyDraftArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    recipient: str | None = Field(default=None, max_length=320)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10000)


class AskUserArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=1000)


class DoneArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    summary: str = Field(min_length=1, max_length=1000)
