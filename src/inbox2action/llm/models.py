from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class TriageDecision(str, Enum):
    IGNORE = "IGNORE"
    NOTIFY = "NOTIFY"
    ACTION_REQUIRED = "ACTION_REQUIRED"


class EmailTriageResult(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    decision: TriageDecision
    reason: str = Field(min_length=1, max_length=1000)
    confidence: float = Field(ge=0.0, le=1.0)


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ChatCompletionResult:
    model: str
    content: str | None
    finish_reason: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    tool_calls: tuple[ToolCall, ...] = ()
    reasoning_content: str | None = field(default=None, repr=False, compare=False)

    @property
    def reasoning_present(self) -> bool:
        return self.reasoning_content is not None

    @property
    def reasoning_length(self) -> int:
        return len(self.reasoning_content or "")

    @property
    def reasoning_sha256(self) -> str | None:
        if self.reasoning_content is None:
            return None
        return hashlib.sha256(self.reasoning_content.encode("utf-8")).hexdigest()
