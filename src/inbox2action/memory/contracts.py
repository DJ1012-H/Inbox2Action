"""Typed contracts for Stage 9 memory and trusted user edit evidence.

The contracts deliberately contain preference summaries rather than provider
payloads.  In particular, reply bodies are reduced to bounded style features
before they can cross the long-term-memory boundary.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import StrEnum
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = 1
_MAX_EVIDENCE = 200
_SAFE_KEY = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_CLOCK = re.compile(r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
_FORBIDDEN_FIELDS = frozenset(
    {
        "body",
        "raw_body",
        "raw_email",
        "raw_mime",
        "html",
        "attachment",
        "oauth_token",
        "api_key",
        "authorization_header",
        "database_password",
        "provider_client",
        "db_session",
        "http_client",
    }
)


class MemoryCategory(StrEnum):
    TRIAGE = "triage_preferences"
    REPLY = "reply_preferences"
    TASK = "task_preferences"
    CALENDAR = "calendar_preferences"


class MemoryUpdateOutcome(StrEnum):
    APPLIED = "APPLIED"
    ALREADY_APPLIED = "ALREADY_APPLIED"
    NO_OP = "NO_OP"


class TriagePreferences(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ignored_types: tuple[str, ...] = Field(default=(), max_length=12)
    notify_types: tuple[str, ...] = Field(default=(), max_length=12)
    task_types: tuple[str, ...] = Field(default=(), max_length=12)

    @field_validator("ignored_types", "notify_types", "task_types")
    @classmethod
    def validate_types(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(
            dict.fromkeys(item.strip().casefold() for item in values if item.strip())
        )
        if any(len(item) > 64 for item in normalized):
            raise ValueError("triage type is too long")
        return normalized


class ReplyPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    language: str | None = Field(default=None, max_length=32)
    formality: Literal["casual", "neutral", "formal"] | None = None
    length: Literal["short", "medium", "long"] | None = None
    opening_style: Literal["greeting", "direct", "none"] | None = None
    closing_style: Literal["thanks", "signature", "none"] | None = None
    expression_patterns: tuple[str, ...] = Field(default=(), max_length=5)

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized or any(ord(char) < 32 for char in normalized):
            raise ValueError("language must be a bounded label")
        return normalized

    @field_validator("expression_patterns")
    @classmethod
    def validate_expression_patterns(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(
            dict.fromkeys(item.strip() for item in values if item.strip())
        )
        if any(len(item) > 80 for item in normalized):
            raise ValueError("expression pattern is too long")
        return normalized


class TaskPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    default_priority: Literal["low", "medium", "high"] | None = None
    deadline_interpretation: (
        Literal["explicit_only", "calendar_days", "business_days"] | None
    ) = None
    summary_preferred: bool | None = None


class WorkingHours(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    start: str = Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    end: str = Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")

    @model_validator(mode="after")
    def validate_order(self) -> WorkingHours:
        if self.end <= self.start:
            raise ValueError("working hours must end after start")
        return self


class CalendarPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    working_hours: WorkingHours | None = None
    preferred_duration_minutes: int | None = Field(default=None, ge=15, le=480)
    lunch_period: WorkingHours | None = None
    preferred_windows: tuple[str, ...] = Field(default=(), max_length=6)
    reminder_minutes: int | None = Field(default=None, ge=0, le=1440)

    @field_validator("preferred_windows")
    @classmethod
    def validate_windows(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(
            dict.fromkeys(item.strip() for item in values if item.strip())
        )
        if any(not _CLOCK.fullmatch(item) for item in normalized):
            raise ValueError("preferred calendar windows must be HH:MM")
        return normalized


type MemoryPreferences = (
    TriagePreferences | ReplyPreferences | TaskPreferences | CalendarPreferences
)


def _preference_model(category: MemoryCategory, value: object) -> MemoryPreferences:
    model_type: type[BaseModel]
    if category is MemoryCategory.TRIAGE:
        model_type = TriagePreferences
    elif category is MemoryCategory.REPLY:
        model_type = ReplyPreferences
    elif category is MemoryCategory.TASK:
        model_type = TaskPreferences
    else:
        model_type = CalendarPreferences
    return cast(MemoryPreferences, model_type.model_validate(value))


class MemoryDocument(BaseModel):
    """One category snapshot stored under the category's owner namespace."""

    model_config = ConfigDict(extra="forbid")

    record_type: Literal["memory_state"] = "memory_state"
    category: MemoryCategory
    schema_version: int = Field(default=SCHEMA_VERSION, ge=1, le=SCHEMA_VERSION)
    version: int = Field(ge=0)
    preferences: dict[str, object] = Field(default_factory=dict)
    evidence_count: int = Field(default=0, ge=0, le=_MAX_EVIDENCE)
    updated_at: datetime

    @model_validator(mode="after")
    def validate_category_preferences(self) -> MemoryDocument:
        typed = _preference_model(self.category, self.preferences)
        self.preferences = typed.model_dump(mode="json")
        if self.version != self.evidence_count:
            raise ValueError("memory version must equal applied evidence count")
        return self

    def typed_preferences(self) -> MemoryPreferences:
        return _preference_model(self.category, self.preferences)


class UserEditDiff(BaseModel):
    """A safe, replay-identifiable summary of one human correction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    category: MemoryCategory
    thread_id: str = Field(min_length=1, max_length=128)
    action_id: str = Field(min_length=1, max_length=128)
    approval_revision: int = Field(ge=1)
    before: dict[str, object] = Field(default_factory=dict)
    after: dict[str, object] = Field(default_factory=dict)
    changed_fields: tuple[str, ...] = Field(default=(), max_length=16)
    preference_updates: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_diff(self) -> UserEditDiff:
        changed = tuple(
            sorted(
                set(self.before)
                .union(self.after)
                .difference(
                    key
                    for key in set(self.before).intersection(self.after)
                    if self.before[key] == self.after[key]
                )
            )
        )
        if self.changed_fields and self.changed_fields != changed:
            raise ValueError("changed_fields does not match before/after")
        object.__setattr__(self, "changed_fields", changed)
        for key in (*self.before, *self.after, *self.preference_updates):
            if not _SAFE_KEY.fullmatch(key):
                raise ValueError("memory field name is not safe")
            if key in _FORBIDDEN_FIELDS:
                raise ValueError("raw or secret fields cannot enter memory evidence")
        _validate_safe_value(self.before)
        _validate_safe_value(self.after)
        _validate_safe_value(self.preference_updates)
        return self

    @property
    def evidence_id(self) -> str:
        payload = {
            "category": self.category.value,
            "thread_id": self.thread_id,
            "action_id": self.action_id,
            "approval_revision": self.approval_revision,
            "before": self.before,
            "after": self.after,
            "changed_fields": self.changed_fields,
            "preference_updates": self.preference_updates,
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @property
    def is_no_op(self) -> bool:
        return not self.changed_fields or not self.preference_updates

    @classmethod
    def from_action_edit(
        cls,
        *,
        thread_id: str,
        approval_revision: int,
        before_parameters: dict[str, object],
        after_parameters: dict[str, object],
        action_id: str,
        tool_name: str,
    ) -> UserEditDiff:
        category = _category_for_tool(tool_name)
        if category is MemoryCategory.TASK:
            before = {
                "priority": before_parameters.get("priority"),
            }
            after = {"priority": after_parameters.get("priority")}
            updates: dict[str, object] = {}
            if (
                before["priority"] != after["priority"]
                and after["priority"] is not None
            ):
                updates["default_priority"] = after["priority"]
        elif category is MemoryCategory.CALENDAR:
            before = _calendar_features(before_parameters)
            after = _calendar_features(after_parameters)
            updates = {}
            if before.get("duration_minutes") != after.get("duration_minutes"):
                updates["preferred_duration_minutes"] = after.get("duration_minutes")
        elif category is MemoryCategory.REPLY:
            before = _reply_features(before_parameters.get("body"))
            after = _reply_features(after_parameters.get("body"))
            updates = {
                key: value
                for key, value in after.items()
                if key
                in {"language", "formality", "length", "opening_style", "closing_style"}
                and before.get(key) != value
            }
        else:
            before = {}
            after = {}
            updates = {}
        return cls(
            category=category,
            thread_id=thread_id,
            action_id=action_id,
            approval_revision=approval_revision,
            before=before,
            after=after,
            preference_updates=updates,
        )

    @classmethod
    def from_triage_correction(
        cls,
        *,
        thread_id: str,
        approval_revision: int,
        message_type: str,
        before_decision: str,
        after_decision: str,
    ) -> UserEditDiff:
        normalized_type = message_type.strip().casefold()
        normalized_after = after_decision.strip().upper()
        if not normalized_type or normalized_after not in {
            "IGNORE",
            "NOTIFY",
            "ACTION_REQUIRED",
        }:
            raise ValueError("triage correction is invalid")
        return cls(
            category=MemoryCategory.TRIAGE,
            thread_id=thread_id,
            action_id="triage",
            approval_revision=approval_revision,
            before={"decision": before_decision, "message_type": normalized_type},
            after={"decision": normalized_after, "message_type": normalized_type},
            preference_updates={
                "decision": normalized_after,
                "message_type": normalized_type,
            },
        )


class MemoryEvidence(BaseModel):
    """The only durable write produced by a trusted user edit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    record_type: Literal["memory_evidence"] = "memory_evidence"
    evidence_id: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    category: MemoryCategory
    schema_version: int = Field(default=SCHEMA_VERSION, ge=1, le=SCHEMA_VERSION)
    memory_version: int = Field(ge=1, le=_MAX_EVIDENCE)
    thread_id: str = Field(min_length=1, max_length=128)
    action_id: str = Field(min_length=1, max_length=128)
    approval_revision: int = Field(ge=1)
    changed_fields: tuple[str, ...] = Field(max_length=16)
    before: dict[str, object] = Field(default_factory=dict)
    after: dict[str, object] = Field(default_factory=dict)
    preference_updates: dict[str, object] = Field(default_factory=dict)
    source: Literal["user_edit"] = "user_edit"
    created_at: datetime

    @model_validator(mode="after")
    def validate_evidence_payload(self) -> MemoryEvidence:
        for key in (*self.before, *self.after, *self.preference_updates):
            if key in _FORBIDDEN_FIELDS or not _SAFE_KEY.fullmatch(key):
                raise ValueError("raw or secret fields cannot enter memory evidence")
        _validate_safe_value(self.before)
        _validate_safe_value(self.after)
        _validate_safe_value(self.preference_updates)
        allowed = {
            MemoryCategory.TRIAGE: {"decision", "message_type"},
            MemoryCategory.REPLY: {
                "language",
                "formality",
                "length",
                "opening_style",
                "closing_style",
            },
            MemoryCategory.TASK: {
                "default_priority",
                "deadline_interpretation",
                "summary_preferred",
            },
            MemoryCategory.CALENDAR: {
                "working_hours",
                "preferred_duration_minutes",
                "lunch_period",
                "preferred_windows",
                "reminder_minutes",
            },
        }[self.category]
        if set(self.preference_updates).difference(allowed):
            raise ValueError("evidence update is outside the category contract")
        return self


def memory_owner_id(account_id: str) -> str:
    """Normalize the trusted provider account identity for memory ownership."""

    normalized = account_id.strip().casefold()
    if (
        not normalized
        or len(normalized) > 128
        or any(ord(char) < 32 for char in normalized)
    ):
        raise ValueError("account_id is not a valid memory owner")
    return normalized


def memory_owner_key(account_id: str) -> str:
    """Map one trusted account identity to a stable namespace-safe label."""

    owner = memory_owner_id(account_id)
    digest = hashlib.sha256(owner.encode("utf-8")).hexdigest()
    return f"acct-{digest}"


def memory_namespace(
    account_id: str, category: MemoryCategory
) -> tuple[str, str, str]:
    """Return the sole LangGraph namespace contract for Stage 9 memory."""

    return ("memory", memory_owner_key(account_id), category.value)


def _category_for_tool(tool_name: str) -> MemoryCategory:
    if tool_name == "save_reply_draft":
        return MemoryCategory.REPLY
    if tool_name in {"save_task_proposal", "create_clickup_task"}:
        return MemoryCategory.TASK
    if tool_name in {"save_calendar_proposal", "create_calendar_event"}:
        return MemoryCategory.CALENDAR
    raise ValueError("Tool cannot produce preference memory")


def _calendar_features(parameters: dict[str, object]) -> dict[str, object]:
    start = _parse_datetime(parameters.get("start_time", parameters.get("start")))
    end = _parse_datetime(parameters.get("end_time", parameters.get("end")))
    if start is None or end is None or end <= start:
        return {}
    return {"duration_minutes": int((end - start).total_seconds() // 60)}


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else None
    return None


def _reply_features(value: object) -> dict[str, object]:
    if not isinstance(value, str) or not value.strip():
        return {}
    text = value.strip()
    lower = text.casefold()
    cjk = sum("\u4e00" <= char <= "\u9fff" for char in text)
    alpha = sum(char.isalpha() for char in text)
    language = "zh" if cjk >= 2 and cjk >= max(1, alpha // 4) else "en"
    formality = (
        "formal"
        if any(
            token in lower
            for token in ("dear ", "尊敬的", "please kindly", "best regards")
        )
        else "neutral"
    )
    length = "short" if len(text) <= 160 else "long" if len(text) >= 600 else "medium"
    first_line = text.splitlines()[0].casefold()
    last_line = text.splitlines()[-1].casefold()
    opening_style = (
        "greeting"
        if any(token in first_line for token in ("dear", "hello", "hi ", "您好"))
        else "direct"
    )
    closing_style = (
        "thanks"
        if "thank" in last_line or "谢谢" in last_line
        else "signature"
        if len(last_line) <= 80
        else "none"
    )
    return {
        "language": language,
        "formality": formality,
        "length": length,
        "opening_style": opening_style,
        "closing_style": closing_style,
    }


def _validate_safe_value(value: object) -> None:
    if isinstance(value, str):
        if len(value) > 256 or any(
            ord(char) < 32 and char not in "\t\n" for char in value
        ):
            raise ValueError("memory evidence contains an unsafe string")
        return
    if isinstance(value, (int, float, bool)) or value is None:
        return
    if isinstance(value, list | tuple):
        if len(value) > 16:
            raise ValueError("memory evidence list is too long")
        for item in value:
            _validate_safe_value(item)
        return
    if isinstance(value, dict):
        if len(value) > 32:
            raise ValueError("memory evidence object is too large")
        for key, item in value.items():
            if not isinstance(key, str) or not _SAFE_KEY.fullmatch(key):
                raise ValueError("memory evidence key is unsafe")
            _validate_safe_value(item)
        return
    raise ValueError("memory evidence contains a non-serializable value")
