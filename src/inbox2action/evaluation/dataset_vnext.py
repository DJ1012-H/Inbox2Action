"""Candidate-only vNext dataset contracts and fail-closed validation."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Callable, Iterable
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

SCHEMA_VERSION: Literal["2.0"] = "2.0"
DATASET_VERSION: Literal["inbox2action-vnext-candidate-1"] = (
    "inbox2action-vnext-candidate-1"
)
_SAFE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,95}$"
_SAFE_ID_RE = re.compile(_SAFE_ID_PATTERN)
SafeId = Annotated[str, Field(min_length=3, max_length=96, pattern=_SAFE_ID_PATTERN)]


class DatasetSplit(str, Enum):
    DEVELOPMENT = "development"
    REGRESSION = "regression"
    SECURITY_CHALLENGE = "security_challenge"


class EmailCategory(str, Enum):
    ORDINARY = "ordinary"
    NOTIFICATION = "notification"
    TASK = "task"
    CALENDAR = "calendar"
    MULTI_ACTION = "multi_action"
    PROMPT_INJECTION = "prompt_injection"


class TriageDecision(str, Enum):
    IGNORE = "IGNORE"
    NOTIFY = "NOTIFY"
    ACTION_REQUIRED = "ACTION_REQUIRED"


class CandidateReviewStatus(str, Enum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    REJECTED = "rejected"


class WorkflowScenarioType(str, Enum):
    DUPLICATE_DELIVERY = "duplicate_delivery"
    APPROVAL_EDIT = "approval_edit"
    STALE_APPROVAL = "stale_approval"
    RESTART_RECOVERY = "restart_recovery"
    PROVIDER_FAILURE = "provider_failure"
    PROVIDER_UNKNOWN = "provider_unknown"
    PAYLOAD_HASH_MISMATCH = "payload_hash_mismatch"
    DEPENDENCY_ORDER = "dependency_order"
    REJECTION = "rejection"
    RETRY_AFTER_FAILURE = "retry_after_failure"


class AttachmentMetadataVNext(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    attachment_id: SafeId
    filename: str = Field(min_length=1, max_length=255)
    media_type: str = Field(min_length=3, max_length=128)
    size_bytes: int = Field(ge=0, le=25_000_000)
    inline: bool = False
    content_disposition: Literal["attachment", "inline"] = "attachment"
    synthetic_only: Literal[True] = True


class EmailEnvelopeVNext(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    account_id: SafeId
    message_id: str = Field(min_length=3, max_length=256)
    provider_thread_id: str | None = Field(default=None, max_length=256)
    from_address: str = Field(min_length=13, max_length=320)
    reply_to: str | None = Field(default=None, max_length=320)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=50_000)
    html: str | None = Field(default=None, max_length=100_000)
    received_at: datetime
    headers: dict[str, str] = Field(default_factory=dict)
    attachments: list[AttachmentMetadataVNext] = Field(default_factory=list)

    @field_validator("from_address", "reply_to")
    @classmethod
    def require_synthetic_address(cls, value: str | None) -> str | None:
        if value is None:
            return None
        local_part, separator, domain = value.rpartition("@")
        if (
            not separator
            or not local_part
            or domain.casefold() not in {"example.com", "example.test"}
            or any(character.isspace() for character in value)
        ):
            raise ValueError("addresses must use a synthetic example domain")
        return value

    @field_validator("received_at")
    @classmethod
    def require_received_offset(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("received_at must include an explicit offset")
        return value

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > 32:
            raise ValueError("too many synthetic headers")
        for name, item in value.items():
            if not name or len(name) > 128 or "\n" in name or "\r" in name:
                raise ValueError("invalid header name")
            if len(item) > 1_000 or "\n" in item or "\r" in item:
                raise ValueError("invalid header value")
        return value

    @model_validator(mode="after")
    def validate_attachment_ids(self) -> EmailEnvelopeVNext:
        identifiers = [item.attachment_id for item in self.attachments]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("attachment IDs must be unique within an email")
        return self


class NormalizationExpectationVNext(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    contains_all: list[str] = Field(default_factory=list)
    excludes_all: list[str] = Field(default_factory=list)
    minimum_redactions: int = Field(default=0, ge=0)
    minimum_tracking_parameters_removed: int = Field(default=0, ge=0)
    expect_truncated: bool = False
    hidden_content_removed: bool = False
    quoted_history_removed: bool = False

    @model_validator(mode="after")
    def validate_fragments(self) -> NormalizationExpectationVNext:
        for values in (self.contains_all, self.excludes_all):
            if len(values) != len(set(values)) or any(not value for value in values):
                raise ValueError("normalization fragments must be non-empty and unique")
        if set(self.contains_all).intersection(self.excludes_all):
            raise ValueError("normalization fragments cannot be both required and excluded")
        return self


class ExpectedOutcomeVNext(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    triage: TriageDecision
    suspected_prompt_injection: bool
    required_capabilities: list[str]
    forbidden_capabilities: list[str]
    requires_user_clarification: bool = False
    requires_approval: bool = False
    normalization: NormalizationExpectationVNext
    maximum_external_side_effects: Literal[0] = 0
    maximum_unauthorized_writes: Literal[0] = 0
    maximum_approval_bypasses: Literal[0] = 0

    @model_validator(mode="after")
    def validate_capabilities(self) -> ExpectedOutcomeVNext:
        for values in (self.required_capabilities, self.forbidden_capabilities):
            if len(values) != len(set(values)):
                raise ValueError("capability lists must not contain duplicates")
            if any(not _SAFE_ID_RE.fullmatch(value) for value in values):
                raise ValueError("capabilities must use safe identifiers")
        if set(self.required_capabilities).intersection(self.forbidden_capabilities):
            raise ValueError("required capabilities cannot be forbidden")
        write_capabilities = {
            "save_reply_draft",
            "save_task_proposal",
            "create_clickup_task",
            "create_calendar_event",
        }
        if write_capabilities.intersection(self.required_capabilities) and not self.requires_approval:
            raise ValueError("write capabilities require approval")
        return self


class EmailDatasetCaseVNext(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["2.0"] = SCHEMA_VERSION
    dataset_version: Literal["inbox2action-vnext-candidate-1"] = DATASET_VERSION
    case_id: SafeId
    split: DatasetSplit
    category: EmailCategory
    subcategory: str = Field(min_length=1, max_length=96, pattern=r"^[a-z0-9_]+$")
    language: Literal["zh-CN", "zh-TW", "en"]
    reference_time: datetime
    timezone: str = Field(min_length=1, max_length=128)
    tags: list[str] = Field(min_length=1)
    envelope: EmailEnvelopeVNext
    expected: ExpectedOutcomeVNext
    fixture_ids: list[SafeId] = Field(default_factory=list)
    workflow_scenario_ids: list[SafeId] = Field(default_factory=list)

    @field_validator("reference_time")
    @classmethod
    def require_reference_offset(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("reference_time must include an explicit offset")
        return value

    @field_validator("timezone")
    @classmethod
    def require_known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a known IANA timezone") from exc
        return value

    @field_validator("tags", "fixture_ids", "workflow_scenario_ids")
    @classmethod
    def require_unique_values(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("list values must be unique")
        return value

    @model_validator(mode="after")
    def validate_security_split(self) -> EmailDatasetCaseVNext:
        if self.split is DatasetSplit.SECURITY_CHALLENGE:
            if self.category is not EmailCategory.PROMPT_INJECTION:
                raise ValueError("security challenge cases must be prompt injection cases")
            if not self.expected.suspected_prompt_injection:
                raise ValueError("security challenge cases must expect injection detection")
        return self


class FixtureOutcome(str, Enum):
    OK = "ok"
    CONFLICT = "conflict"
    FAILED = "failed"
    UNKNOWN = "unknown"


class ProviderFixtureVNext(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["2.0"] = SCHEMA_VERSION
    dataset_version: Literal["inbox2action-vnext-candidate-1"] = DATASET_VERSION
    fixture_id: SafeId
    case_id: SafeId
    capability: SafeId
    request: dict[str, JsonValue]
    outcome: FixtureOutcome
    response: dict[str, JsonValue]
    external_side_effects: Literal[0] = 0
    synthetic_only: Literal[True] = True


class WorkflowExpectationVNext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    terminal_status: Literal[
        "completed",
        "rejected",
        "failed",
        "unknown",
        "blocked",
        "pending",
    ]
    write_attempts: int = Field(ge=0, le=10)
    successful_writes: int = Field(ge=0, le=10)
    duplicate_writes: Literal[0] = 0
    approval_bypasses: Literal[0] = 0
    same_action_identity: bool = True
    requires_reconciliation: bool = False

    @model_validator(mode="after")
    def validate_write_counts(self) -> WorkflowExpectationVNext:
        if self.successful_writes > self.write_attempts:
            raise ValueError("successful writes cannot exceed attempts")
        if self.requires_reconciliation and self.terminal_status not in {
            "unknown",
            "blocked",
        }:
            raise ValueError("reconciliation requires an unknown or blocked state")
        return self


class WorkflowScenarioVNext(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["2.0"] = SCHEMA_VERSION
    dataset_version: Literal["inbox2action-vnext-candidate-1"] = DATASET_VERSION
    scenario_id: SafeId
    case_id: SafeId
    scenario_type: WorkflowScenarioType
    events: list[str] = Field(min_length=1, max_length=12)
    fixture_ids: list[SafeId] = Field(default_factory=list)
    expected: WorkflowExpectationVNext
    deterministic_only: Literal[True] = True

    @field_validator("events", "fixture_ids")
    @classmethod
    def validate_unique_sequence(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("scenario events and fixtures must be unique")
        return value


class CandidateReviewRecordVNext(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["2.0"] = SCHEMA_VERSION
    dataset_version: Literal["inbox2action-vnext-candidate-1"] = DATASET_VERSION
    case_id: SafeId
    reviewer: str = Field(min_length=1, max_length=200)
    reviewed_at: date | None = None
    status: CandidateReviewStatus = CandidateReviewStatus.DRAFT
    notes: str = Field(max_length=2_000)

    @model_validator(mode="after")
    def prevent_automatic_approval(self) -> CandidateReviewRecordVNext:
        if self.status is CandidateReviewStatus.DRAFT and self.reviewed_at is not None:
            raise ValueError("draft candidates cannot have a review date")
        if self.status is not CandidateReviewStatus.DRAFT and self.reviewed_at is None:
            raise ValueError("completed reviews require a review date")
        return self


class DatasetManifestVNext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["dataset-vnext-manifest-1"]
    dataset_version: Literal["inbox2action-vnext-candidate-1"] = DATASET_VERSION
    created_at: date
    asset_state: Literal["candidate_draft"]
    formal_holdout_created: Literal[False] = False
    real_provider_evidence: Literal[False] = False
    case_count: int = Field(ge=1)
    split_counts: dict[str, int]
    category_counts: dict[str, int]
    language_counts: dict[str, int]
    workflow_scenario_count: int = Field(ge=1)
    workflow_type_counts: dict[str, int]
    fixture_count: int = Field(ge=1)
    review_status_counts: dict[str, int]
    required_coverage_tags: list[str] = Field(min_length=1)
    hash_algorithm: Literal["sha256-lf-v1"]
    asset_sha256: dict[str, str]


class DatasetValidationSummaryVNext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["PASS"] = "PASS"
    case_count: int
    split_counts: dict[str, int]
    category_counts: dict[str, int]
    language_counts: dict[str, int]
    workflow_scenario_count: int
    workflow_type_counts: dict[str, int]
    fixture_count: int
    review_status_counts: dict[str, int]
    formal_holdout_created: bool
    real_provider_evidence: bool


def render_jsonl(records: Iterable[BaseModel]) -> str:
    return "".join(
        json.dumps(
            record.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
        for record in records
    )


def lf_sha256(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def load_jsonl[ModelT: BaseModel](
    path: Path,
    model_type: type[ModelT],
    *,
    identifier: Callable[[ModelT], str],
    maximum_records: int = 500,
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
                    raise TypeError("record must be a JSON object")
                record = model_type.model_validate(raw)
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(
                    f"invalid candidate record in {path.name} at line {line_number}"
                ) from exc
            record_id = identifier(record)
            if record_id in identifiers:
                raise ValueError(f"duplicate candidate identifier in {path.name}")
            identifiers.add(record_id)
            records.append(record)
            if len(records) > maximum_records:
                raise ValueError(f"too many records in {path.name}")
    return tuple(records)


def validate_dataset_vnext(root: Path) -> DatasetValidationSummaryVNext:
    root = root.resolve()
    manifest = DatasetManifestVNext.model_validate_json(
        (root / "manifest.json").read_text(encoding="utf-8")
    )
    case_files = {
        DatasetSplit.DEVELOPMENT: root / "cases" / "development.jsonl",
        DatasetSplit.REGRESSION: root / "cases" / "regression.jsonl",
        DatasetSplit.SECURITY_CHALLENGE: root
        / "cases"
        / "security-challenge.jsonl",
    }
    cases: list[EmailDatasetCaseVNext] = []
    for split, path in case_files.items():
        loaded = load_jsonl(
            path,
            EmailDatasetCaseVNext,
            identifier=lambda item: item.case_id,
        )
        if any(item.split is not split for item in loaded):
            raise ValueError("case split does not match its asset file")
        cases.extend(loaded)
    fixtures = load_jsonl(
        root / "fixtures" / "provider-observations.jsonl",
        ProviderFixtureVNext,
        identifier=lambda item: item.fixture_id,
    )
    scenarios = load_jsonl(
        root / "workflow" / "scenarios.jsonl",
        WorkflowScenarioVNext,
        identifier=lambda item: item.scenario_id,
    )
    reviews = load_jsonl(
        root / "reviews" / "review-records.jsonl",
        CandidateReviewRecordVNext,
        identifier=lambda item: item.case_id,
    )

    case_ids = [item.case_id for item in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("case identifiers must be globally unique")
    cases_by_id = {item.case_id: item for item in cases}
    fixtures_by_id = {item.fixture_id: item for item in fixtures}
    if {item.case_id for item in reviews} != set(case_ids):
        raise ValueError("candidate reviews must match cases exactly")
    if any(item.status is not CandidateReviewStatus.DRAFT for item in reviews):
        raise ValueError("Codex-generated candidate reviews must remain draft")

    inverse_scenarios: dict[str, set[str]] = {case_id: set() for case_id in case_ids}
    for scenario in scenarios:
        if scenario.case_id not in cases_by_id:
            raise ValueError("workflow scenario references an unknown case")
        inverse_scenarios[scenario.case_id].add(scenario.scenario_id)
        for fixture_id in scenario.fixture_ids:
            fixture = fixtures_by_id.get(fixture_id)
            if fixture is None or fixture.case_id != scenario.case_id:
                raise ValueError("workflow scenario fixture reference is invalid")

    for case in cases:
        if set(case.workflow_scenario_ids) != inverse_scenarios[case.case_id]:
            raise ValueError("case workflow references are incomplete")
        for fixture_id in case.fixture_ids:
            fixture = fixtures_by_id.get(fixture_id)
            if fixture is None or fixture.case_id != case.case_id:
                raise ValueError("case fixture reference is invalid")
    if any(item.case_id not in cases_by_id for item in fixtures):
        raise ValueError("fixture references an unknown case")

    split_counts = Counter(item.split.value for item in cases)
    category_counts = Counter(item.category.value for item in cases)
    language_counts = Counter(item.language for item in cases)
    workflow_type_counts = Counter(item.scenario_type.value for item in scenarios)
    review_status_counts = Counter(item.status.value for item in reviews)
    tags = {tag for item in cases for tag in item.tags}

    observed = {
        "case_count": len(cases),
        "split_counts": dict(sorted(split_counts.items())),
        "category_counts": dict(sorted(category_counts.items())),
        "language_counts": dict(sorted(language_counts.items())),
        "workflow_scenario_count": len(scenarios),
        "workflow_type_counts": dict(sorted(workflow_type_counts.items())),
        "fixture_count": len(fixtures),
        "review_status_counts": dict(sorted(review_status_counts.items())),
    }
    for field_name, value in observed.items():
        if getattr(manifest, field_name) != value:
            raise ValueError(f"manifest {field_name} does not match assets")
    if not set(manifest.required_coverage_tags).issubset(tags):
        raise ValueError("required coverage tag is missing")
    expected_workflow_types = {item.value for item in WorkflowScenarioType}
    if set(workflow_type_counts) != expected_workflow_types or any(
        count < 3 for count in workflow_type_counts.values()
    ):
        raise ValueError("workflow scenarios do not cover every required type")
    if manifest.formal_holdout_created or (root / "formal-holdout").exists():
        raise ValueError("formal holdout must not exist before candidate freeze")
    if manifest.real_provider_evidence:
        raise ValueError("candidate assets cannot claim real provider evidence")

    for raw_path, expected_hash in manifest.asset_sha256.items():
        candidate = (root / raw_path).resolve()
        if root not in candidate.parents:
            raise ValueError("manifest path escapes the dataset root")
        if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            raise ValueError("manifest hash is invalid")
        if lf_sha256(candidate) != expected_hash:
            raise ValueError("candidate asset hash mismatch")

    return DatasetValidationSummaryVNext(
        case_count=len(cases),
        split_counts=dict(sorted(split_counts.items())),
        category_counts=dict(sorted(category_counts.items())),
        language_counts=dict(sorted(language_counts.items())),
        workflow_scenario_count=len(scenarios),
        workflow_type_counts=dict(sorted(workflow_type_counts.items())),
        fixture_count=len(fixtures),
        review_status_counts=dict(sorted(review_status_counts.items())),
        formal_holdout_created=manifest.formal_holdout_created,
        real_provider_evidence=manifest.real_provider_evidence,
    )
