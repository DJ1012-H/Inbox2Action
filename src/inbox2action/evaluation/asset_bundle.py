"""Load and validate the formal, offline Pilot evaluation asset bundle."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, JsonValue

from inbox2action.evaluation.assets import (
    EvaluationCaseV1,
    ReviewRecordV1,
    ReviewStatus,
    ToolFixtureV1,
    load_evaluation_cases,
    load_review_records,
    load_tool_fixtures,
)

_CATEGORY_FILENAMES: Final = (
    "ordinary.jsonl",
    "task.jsonl",
    "calendar.jsonl",
    "multi_action.jsonl",
    "prompt_injection.jsonl",
)
_SCHEMA_VERSION: Final = "1.0"
_DATASET_VERSION: Final = "deepseek-validation-v1"
_FIXTURE_OBSERVATION_TOOLS: Final = frozenset(
    {"get_current_time", "check_calendar_availability"}
)


class EvaluationAssetConsistencyError(ValueError):
    """A formal asset bundle has an unsafe or unresolved cross-file reference."""


class EvaluationAssetBundleV1(BaseModel):
    """An immutable container for formal cases, fixtures, and review records."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cases: tuple[EvaluationCaseV1, ...]
    fixtures: tuple[ToolFixtureV1, ...]
    reviews: tuple[ReviewRecordV1, ...]


def load_evaluation_asset_bundle(
    evaluation_root: Path,
    *,
    allow_empty: bool = False,
) -> EvaluationAssetBundleV1:
    """Load only the fixed formal asset paths; legacy checkpoint files are ignored."""

    cases: list[EvaluationCaseV1] = []
    for filename in _CATEGORY_FILENAMES:
        path = evaluation_root / "cases" / filename
        if path.exists():
            cases.extend(load_evaluation_cases(path))

    fixtures_path = evaluation_root / "fixtures" / "tool_observations.jsonl"
    reviews_path = evaluation_root / "reviews" / "review-records.jsonl"
    fixtures = load_tool_fixtures(fixtures_path) if fixtures_path.exists() else ()
    reviews = load_review_records(reviews_path) if reviews_path.exists() else ()
    bundle = EvaluationAssetBundleV1(
        cases=tuple(cases), fixtures=fixtures, reviews=reviews
    )
    if not allow_empty and not bundle.cases:
        raise EvaluationAssetConsistencyError("empty_dataset: no formal cases were loaded")
    return bundle


def validate_evaluation_asset_bundle(
    bundle: EvaluationAssetBundleV1,
    *,
    require_approved_reviews: bool = False,
) -> None:
    """Validate safe, deterministic references without exposing content payloads."""

    _validate_versions(bundle)
    cases_by_id = _unique_by_identifier(bundle.cases, "case_id", "duplicate_case_id")
    fixtures_by_id = _unique_by_identifier(
        bundle.fixtures, "fixture_id", "duplicate_fixture_id"
    )
    _validate_fixture_references(bundle, cases_by_id, fixtures_by_id)
    _validate_observation_fixture_coverage(bundle)
    _validate_reviews(bundle, cases_by_id)
    _validate_fixture_match_keys(bundle.fixtures)
    if require_approved_reviews:
        _validate_approval_gate(bundle, cases_by_id)


def _validate_versions(bundle: EvaluationAssetBundleV1) -> None:
    for case in bundle.cases:
        _validate_record_version("case", case.case_id, case)
    for fixture in bundle.fixtures:
        _validate_record_version("fixture", fixture.fixture_id, fixture)
    for review in bundle.reviews:
        _validate_record_version("review", review.case_id, review)


def _validate_record_version(
    asset_type: str,
    identifier: str,
    record: EvaluationCaseV1 | ToolFixtureV1 | ReviewRecordV1,
) -> None:
    if (
        record.schema_version != _SCHEMA_VERSION
        or record.dataset_version != _DATASET_VERSION
    ):
        raise EvaluationAssetConsistencyError(
            f"version_mismatch: {asset_type}_id={identifier}"
        )


def _unique_by_identifier[RecordT](
    records: tuple[RecordT, ...],
    attribute: str,
    error_type: str,
) -> dict[str, RecordT]:
    result: dict[str, RecordT] = {}
    for record in records:
        identifier = getattr(record, attribute)
        if identifier in result:
            raise EvaluationAssetConsistencyError(
                f"{error_type}: {attribute}={identifier}"
            )
        result[identifier] = record
    return result


def _validate_fixture_references(
    bundle: EvaluationAssetBundleV1,
    cases_by_id: Mapping[str, EvaluationCaseV1],
    fixtures_by_id: Mapping[str, ToolFixtureV1],
) -> None:
    referenced_by: dict[str, str] = {}
    for case in bundle.cases:
        for fixture_id in case.tool_fixture_ids:
            fixture = fixtures_by_id.get(fixture_id)
            if fixture is None:
                raise EvaluationAssetConsistencyError(
                    f"missing_fixture: case_id={case.case_id}; fixture_id={fixture_id}"
                )
            if fixture.case_id != case.case_id:
                raise EvaluationAssetConsistencyError(
                    f"fixture_case_mismatch: case_id={case.case_id}; fixture_id={fixture_id}"
                )
            other_case_id = referenced_by.setdefault(fixture_id, case.case_id)
            if other_case_id != case.case_id:
                raise EvaluationAssetConsistencyError(
                    f"fixture_reused_across_cases: fixture_id={fixture_id}"
                )

    for fixture in bundle.fixtures:
        fixture_case = cases_by_id.get(fixture.case_id)
        if fixture_case is None:
            raise EvaluationAssetConsistencyError(
                f"fixture_unknown_case: fixture_id={fixture.fixture_id}; "
                f"case_id={fixture.case_id}"
            )
        if fixture.fixture_id not in fixture_case.tool_fixture_ids:
            raise EvaluationAssetConsistencyError(
                f"orphan_fixture: fixture_id={fixture.fixture_id}; "
                f"case_id={fixture.case_id}"
            )
        sequence_tools = {
            tool
            for sequence in fixture_case.expected.allowed_tool_sequences
            for tool in sequence
        }
        if fixture.tool_name not in sequence_tools:
            raise EvaluationAssetConsistencyError(
                f"fixture_tool_not_allowed: fixture_id={fixture.fixture_id}; "
                f"tool_name={fixture.tool_name}"
            )


def _validate_reviews(
    bundle: EvaluationAssetBundleV1,
    cases_by_id: Mapping[str, EvaluationCaseV1],
) -> None:
    for review in bundle.reviews:
        if review.case_id not in cases_by_id:
            raise EvaluationAssetConsistencyError(
                f"review_unknown_case: case_id={review.case_id}"
            )


def _validate_observation_fixture_coverage(bundle: EvaluationAssetBundleV1) -> None:
    for fixture in bundle.fixtures:
        if fixture.tool_name not in _FIXTURE_OBSERVATION_TOOLS:
            raise EvaluationAssetConsistencyError(
                f"fixture_not_observation_tool: fixture_id={fixture.fixture_id}; "
                f"tool_name={fixture.tool_name}"
            )


def _validate_fixture_match_keys(fixtures: tuple[ToolFixtureV1, ...]) -> None:
    match_keys: set[tuple[str, str, str]] = set()
    for fixture in fixtures:
        try:
            arguments = canonical_json(fixture.arguments_match)
        except (TypeError, ValueError) as exc:
            raise EvaluationAssetConsistencyError(
                f"invalid_match_arguments: fixture_id={fixture.fixture_id}"
            ) from exc
        key = (fixture.case_id, fixture.tool_name, arguments)
        if key in match_keys:
            raise EvaluationAssetConsistencyError(
                f"duplicate_fixture_match_key: fixture_id={fixture.fixture_id}; "
                f"case_id={fixture.case_id}; tool_name={fixture.tool_name}"
            )
        match_keys.add(key)


def _validate_approval_gate(
    bundle: EvaluationAssetBundleV1,
    cases_by_id: Mapping[str, EvaluationCaseV1],
) -> None:
    if not cases_by_id:
        raise EvaluationAssetConsistencyError("approval_gate_empty_dataset")
    reviews_by_case: dict[str, list[ReviewRecordV1]] = defaultdict(list)
    for review in bundle.reviews:
        reviews_by_case[review.case_id].append(review)

    for case_id in cases_by_id:
        reviews = reviews_by_case.get(case_id, [])
        if not reviews:
            raise EvaluationAssetConsistencyError(
                f"approval_review_missing: case_id={case_id}"
            )
        newest_date = max(review.reviewed_at for review in reviews)
        latest_statuses = {
            review.status for review in reviews if review.reviewed_at == newest_date
        }
        if len(latest_statuses) != 1:
            raise EvaluationAssetConsistencyError(
                f"approval_review_conflict: case_id={case_id}"
            )
        if latest_statuses.pop() is not ReviewStatus.APPROVED:
            raise EvaluationAssetConsistencyError(
                f"approval_not_approved: case_id={case_id}"
            )


def canonical_json(value: Mapping[str, JsonValue]) -> str:
    """Return a strict JSON identity string without coercing values or mutating input."""

    _reject_nonstandard_json(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _reject_nonstandard_json(value: object) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite JSON number")
        return
    if isinstance(value, list):
        for item in value:
            _reject_nonstandard_json(item)
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings")
            _reject_nonstandard_json(item)
        return
    raise ValueError("value is not a JSON value")
