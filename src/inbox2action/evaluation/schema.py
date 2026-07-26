from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from inbox2action.llm.models import TriageDecision


class EvaluationCategory(str, Enum):
    ORDINARY = "ordinary"
    TASK = "task"
    SCHEDULE = "schedule"
    MULTI_ACTION = "multi_action"
    PROMPT_INJECTION = "prompt_injection"


class SafetyOutcome(str, Enum):
    NO_EXTERNAL_SIDE_EFFECT = "no_external_side_effect"
    REQUIRES_REPLAN = "requires_replan"
    BLOCKED_UNKNOWN_TOOL = "blocked_unknown_tool"
    BLOCKED_PROMPT_INJECTION = "blocked_prompt_injection"
    WAITING_FOR_USER = "waiting_for_user"


class EvaluationCase(BaseModel):
    """Strict, synthetic input contract for a stage-two evaluation case."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    case_id: str = Field(
        min_length=3, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$"
    )
    category: EvaluationCategory
    language: str = Field(min_length=2, max_length=32)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10000)
    expected_triage: TriageDecision
    expected_tools: list[str] = Field(min_length=1, max_length=20)
    expected_tool_sequence: list[str] = Field(min_length=1, max_length=20)
    expected_safety_outcome: SafetyOutcome
    expected_required_fields: list[str] = Field(max_length=20)
    notes: str = Field(default="", max_length=2000)

    @field_validator("expected_tools", "expected_tool_sequence")
    @classmethod
    def validate_tool_names(cls, value: list[str]) -> list[str]:
        if any(not name.strip() or len(name) > 128 for name in value):
            raise ValueError("tool names must be non-empty and bounded")
        return value

    @field_validator("expected_required_fields")
    @classmethod
    def validate_required_fields(cls, value: list[str]) -> list[str]:
        if any(not name.strip() or len(name) > 128 for name in value):
            raise ValueError("required field names must be non-empty and bounded")
        return value

    @model_validator(mode="after")
    def validate_expectations(self) -> EvaluationCase:
        expected = set(self.expected_tools)
        if not expected.issubset(self.expected_tool_sequence):
            raise ValueError("expected_tools must appear in expected_tool_sequence")
        if len(set(self.expected_tools)) != len(self.expected_tools):
            raise ValueError("expected_tools must not contain duplicates")
        return self


class EvaluationDataset(BaseModel):
    """A bounded collection of validated synthetic cases."""

    model_config = ConfigDict(extra="forbid")

    cases: list[EvaluationCase] = Field(min_length=1, max_length=60)

    @model_validator(mode="after")
    def validate_case_ids(self) -> EvaluationDataset:
        ids = [case.case_id for case in self.cases]
        if len(set(ids)) != len(ids):
            raise ValueError("case_id values must be unique")
        return self


def load_jsonl(path: Path) -> EvaluationDataset:
    """Load only strict JSON objects; input bodies are never logged on errors."""

    cases: list[EvaluationCase] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                raw: Any = json.loads(line)
                cases.append(EvaluationCase.model_validate(raw))
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"invalid evaluation case at line {line_number}"
                ) from exc
    return EvaluationDataset(cases=cases)
