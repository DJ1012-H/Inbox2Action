"""Versioned, reviewable assets for the formal Pilot evaluation dataset."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Annotated, Final, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationError,
    field_validator,
    model_validator,
)

from inbox2action.llm.models import TriageDecision

_SCHEMA_VERSION: Final = "1.0"
_DATASET_VERSION: Final = "deepseek-validation-v1"
_CASE_ID_PATTERN = r"^[A-Za-z0-9._-]{3,64}$"
_TOOL_NAME = Annotated[str, Field(min_length=1, max_length=128)]


class EvaluationCategoryV1(str, Enum):
    ORDINARY = "ordinary"
    TASK = "task"
    CALENDAR = "calendar"
    MULTI_ACTION = "multi_action"
    PROMPT_INJECTION = "prompt_injection"


class ReviewStatus(str, Enum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    REJECTED = "rejected"


class EmailMessageV1(BaseModel):
    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, populate_by_name=True
    )

    from_address: str = Field(alias="from", min_length=13, max_length=254)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10_000)

    @field_validator("from_address")
    @classmethod
    def validate_synthetic_sender(cls, value: str) -> str:
        local_part, separator, domain = value.rpartition("@")
        if not separator or not local_part or domain.casefold() != "example.com":
            raise ValueError("from must be a synthetic example.com address")
        if any(character.isspace() for character in value):
            raise ValueError("from must not contain whitespace")
        return value


class SafetyExpectationsV1(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    external_side_effects: int = Field(default=0, ge=0)
    unknown_tool_executions: int = Field(default=0, ge=0)
    unauthorized_write_operations: int = Field(default=0, ge=0)
    secret_disclosures: int = Field(default=0, ge=0)
    approval_bypasses: int = Field(default=0, ge=0)
    loop_exceeded: bool = False
    requires_replan_after_observation: bool = False
    requires_user_clarification_after_conflict: bool = False


class ExpectedOutcomeV1(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    triage: TriageDecision
    required_tools: list[_TOOL_NAME]
    allowed_tool_sequences: list[list[_TOOL_NAME]] = Field(min_length=1)
    forbidden_tools: list[_TOOL_NAME]
    argument_assertions: dict[str, dict[str, JsonValue]]
    safety: SafetyExpectationsV1

    @model_validator(mode="after")
    def validate_tool_contract(self) -> ExpectedOutcomeV1:
        collections = {
            "required_tools": self.required_tools,
            "forbidden_tools": self.forbidden_tools,
        }
        for name, values in collections.items():
            if len(values) != len(set(values)):
                raise ValueError(f"{name} must not contain duplicates")

        normalized_sequences: set[tuple[str, ...]] = set()
        for sequence in self.allowed_tool_sequences:
            if not sequence:
                raise ValueError("allowed_tool_sequences must not contain empty sequences")
            if len(sequence) != len(set(sequence)):
                raise ValueError("allowed tool sequences must not contain duplicates")
            sequence_key = tuple(sequence)
            if sequence_key in normalized_sequences:
                raise ValueError("allowed_tool_sequences must not repeat a sequence")
            normalized_sequences.add(sequence_key)
            if not set(self.required_tools).issubset(sequence):
                raise ValueError(
                    "every allowed tool sequence must include all required_tools"
                )

        forbidden = set(self.forbidden_tools)
        if forbidden.intersection(self.required_tools):
            raise ValueError("forbidden_tools must not appear in required_tools")
        if any(forbidden.intersection(sequence) for sequence in self.allowed_tool_sequences):
            raise ValueError("forbidden_tools must not appear in allowed tool sequences")

        sequence_tools = {
            tool for sequence in self.allowed_tool_sequences for tool in sequence
        }
        unknown_assertion_tools = set(self.argument_assertions).difference(sequence_tools)
        if unknown_assertion_tools:
            raise ValueError(
                "argument_assertions keys must appear in an allowed tool sequence"
            )
        return self


class EvaluationCaseV1(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["1.0"] = _SCHEMA_VERSION
    dataset_version: Literal["deepseek-validation-v1"] = _DATASET_VERSION
    case_id: str = Field(min_length=3, max_length=64, pattern=_CASE_ID_PATTERN)
    category: EvaluationCategoryV1
    subcategory: str = Field(min_length=1, max_length=80)
    language: str = Field(min_length=2, max_length=32)
    current_time: datetime
    timezone: str = Field(min_length=1, max_length=128)
    email: EmailMessageV1
    user_context: dict[str, JsonValue]
    expected: ExpectedOutcomeV1
    tool_fixture_ids: list[str]

    @field_validator("tool_fixture_ids")
    @classmethod
    def validate_fixture_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("tool_fixture_ids must not contain duplicates")
        if any(
            not fixture_id or not re.fullmatch(_CASE_ID_PATTERN, fixture_id)
            for fixture_id in value
        ):
            raise ValueError("tool_fixture_ids must use the safe identifier format")
        return value

    @model_validator(mode="after")
    def validate_time_context(self) -> EvaluationCaseV1:
        if self.current_time.tzinfo is None or self.current_time.utcoffset() is None:
            raise ValueError("current_time must include a timezone offset")
        try:
            declared_timezone = ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        expected_offset = self.current_time.astimezone(declared_timezone).utcoffset()
        if self.current_time.utcoffset() != expected_offset:
            raise ValueError("current_time offset must match the declared timezone")
        return self


class ToolFixtureV1(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["1.0"] = _SCHEMA_VERSION
    dataset_version: Literal["deepseek-validation-v1"] = _DATASET_VERSION
    fixture_id: str = Field(min_length=3, max_length=64, pattern=_CASE_ID_PATTERN)
    case_id: str = Field(min_length=3, max_length=64, pattern=_CASE_ID_PATTERN)
    tool_name: _TOOL_NAME
    arguments_match: dict[str, JsonValue]
    observation: dict[str, JsonValue]


class ReviewRecordV1(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["1.0"] = _SCHEMA_VERSION
    dataset_version: Literal["deepseek-validation-v1"] = _DATASET_VERSION
    case_id: str = Field(min_length=3, max_length=64, pattern=_CASE_ID_PATTERN)
    reviewer: str = Field(min_length=1, max_length=200)
    reviewed_at: date
    status: ReviewStatus = ReviewStatus.DRAFT
    changes: list[str]
    notes: str = Field(default="", max_length=4_000)


def _load_jsonl[ModelT: BaseModel](
    path: Path,
    model_type: type[ModelT],
    *,
    unique_identifier: Callable[[ModelT], str] | None = None,
    maximum_records: int | None = None,
) -> tuple[ModelT, ...]:
    records: list[ModelT] = []
    identifiers: set[str] = set()
    with path.open("r", encoding="utf-8", newline="") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
                if not isinstance(raw, dict):
                    raise TypeError("a JSON object is required")
                record = model_type.model_validate(raw)
            except (json.JSONDecodeError, TypeError, ValidationError, ValueError) as exc:
                raise ValueError(
                    f"invalid JSONL record in {path} at line {line_number}"
                ) from exc
            if maximum_records is not None and len(records) >= maximum_records:
                raise ValueError(f"too many JSONL records in {path} at line {line_number}")
            if unique_identifier is not None:
                identifier = unique_identifier(record)
                if identifier in identifiers:
                    raise ValueError(
                        f"duplicate identifier in {path} at line {line_number}"
                    )
                identifiers.add(identifier)
            records.append(record)
    return tuple(records)


def load_evaluation_cases(path: Path) -> tuple[EvaluationCaseV1, ...]:
    return _load_jsonl(
        path,
        EvaluationCaseV1,
        unique_identifier=lambda case: case.case_id,
        maximum_records=60,
    )


def load_tool_fixtures(path: Path) -> tuple[ToolFixtureV1, ...]:
    return _load_jsonl(
        path,
        ToolFixtureV1,
        unique_identifier=lambda fixture: fixture.fixture_id,
    )


def load_review_records(path: Path) -> tuple[ReviewRecordV1, ...]:
    return _load_jsonl(path, ReviewRecordV1)
