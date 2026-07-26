from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from inbox2action.evaluation.asset_bundle import (
    EvaluationAssetBundleV1,
    EvaluationAssetConsistencyError,
    load_evaluation_asset_bundle,
    validate_evaluation_asset_bundle,
)
from inbox2action.evaluation.assets import (
    EvaluationCaseV1,
    ReviewRecordV1,
    ToolFixtureV1,
)


def make_case(
    case_id: str = "case-001", fixture_ids: list[str] | None = None
) -> EvaluationCaseV1:
    return EvaluationCaseV1.model_validate(
        {
            "schema_version": "1.0",
            "dataset_version": "deepseek-validation-v1",
            "case_id": case_id,
            "category": "task",
            "subcategory": "synthetic",
            "language": "en",
            "current_time": "2026-07-26T09:00:00+08:00",
            "timezone": "Asia/Shanghai",
            "email": {
                "from": "sender@example.com",
                "subject": "Synthetic task",
                "body": "Synthetic test message only.",
            },
            "user_context": {},
            "expected": {
                "triage": "ACTION_REQUIRED",
                "required_tools": ["get_current_time"],
                "allowed_tool_sequences": [["get_current_time", "done"]],
                "forbidden_tools": [],
                "argument_assertions": {},
                "safety": {},
            },
            "tool_fixture_ids": fixture_ids or [],
        }
    )


def make_fixture(
    fixture_id: str = "fixture-001",
    case_id: str = "case-001",
    tool_name: str = "get_current_time",
    arguments: dict[str, object] | None = None,
) -> ToolFixtureV1:
    return ToolFixtureV1.model_validate(
        {
            "schema_version": "1.0",
            "dataset_version": "deepseek-validation-v1",
            "fixture_id": fixture_id,
            "case_id": case_id,
            "tool_name": tool_name,
            "arguments_match": arguments or {},
            "observation": {"kind": "synthetic", "nested": {"value": 1}},
        }
    )


def make_review(status: str = "approved", reviewed_at: str = "2026-07-26") -> ReviewRecordV1:
    return ReviewRecordV1.model_validate(
        {
            "schema_version": "1.0",
            "dataset_version": "deepseek-validation-v1",
            "case_id": "case-001",
            "reviewer": "Human Reviewer",
            "reviewed_at": reviewed_at,
            "status": status,
            "changes": [],
        }
    )


def make_bundle(
    *,
    cases: tuple[EvaluationCaseV1, ...] = (),
    fixtures: tuple[ToolFixtureV1, ...] = (),
    reviews: tuple[ReviewRecordV1, ...] = (),
) -> EvaluationAssetBundleV1:
    return EvaluationAssetBundleV1(cases=cases, fixtures=fixtures, reviews=reviews)


def test_loads_five_category_files_in_fixed_order(tmp_path: Path) -> None:
    root = tmp_path / "evaluation"
    for index, filename in enumerate(
        ["ordinary", "task", "calendar", "multi_action", "prompt_injection"], 1
    ):
        path = root / "cases" / f"{filename}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = make_case(f"case-{index:03d}").model_dump(mode="json", by_alias=True)
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    bundle = load_evaluation_asset_bundle(root)
    assert [case.case_id for case in bundle.cases] == [
        "case-001", "case-002", "case-003", "case-004", "case-005"
    ]


def test_missing_category_files_and_legacy_checkpoint_are_ignored(tmp_path: Path) -> None:
    root = tmp_path / "evaluation"
    legacy = root / "fixtures" / "checkpoint-3-sample.jsonl"
    legacy.parent.mkdir(parents=True)
    legacy.write_text('{"body":"never loaded"}\n', encoding="utf-8")
    bundle = load_evaluation_asset_bundle(root, allow_empty=True)
    assert bundle.cases == ()
    assert bundle.fixtures == ()
    validate_evaluation_asset_bundle(bundle)


def test_empty_dataset_requires_explicit_allowance(tmp_path: Path) -> None:
    with pytest.raises(EvaluationAssetConsistencyError, match="empty_dataset"):
        load_evaluation_asset_bundle(tmp_path / "evaluation")
    assert load_evaluation_asset_bundle(tmp_path / "evaluation", allow_empty=True).cases == ()


@pytest.mark.parametrize(
    ("bundle", "error"),
    [
        (
            make_bundle(cases=(make_case(), make_case())),
            "duplicate_case_id",
        ),
        (
            make_bundle(
                cases=(make_case(fixture_ids=["fixture-001", "fixture-002"]),),
                fixtures=(make_fixture(), make_fixture("fixture-001")),
            ),
            "duplicate_fixture_id",
        ),
        (make_bundle(cases=(make_case(fixture_ids=["missing-001"]),)), "missing_fixture"),
        (
            make_bundle(
                cases=(make_case(),), fixtures=(make_fixture(case_id="missing-case"),)
            ),
            "fixture_unknown_case",
        ),
        (
            make_bundle(
                cases=(make_case(fixture_ids=["fixture-001"]),),
                fixtures=(make_fixture(case_id="case-002"),),
            ),
            "fixture_case_mismatch",
        ),
        (
            make_bundle(cases=(make_case(),), fixtures=(make_fixture(),)),
            "orphan_fixture",
        ),
        (
            make_bundle(
                cases=(make_case(fixture_ids=["fixture-001"]),),
                fixtures=(make_fixture(tool_name="save_reply_draft"),),
            ),
            "fixture_tool_not_allowed",
        ),
        (
            make_bundle(
                cases=(make_case(fixture_ids=["fixture-001", "fixture-002"]),),
                fixtures=(
                    make_fixture(arguments={"a": 1, "b": ["x"]}),
                    make_fixture("fixture-002", arguments={"b": ["x"], "a": 1}),
                ),
            ),
            "duplicate_fixture_match_key",
        ),
    ],
)
def test_rejects_inconsistent_case_fixture_references(
    bundle: EvaluationAssetBundleV1, error: str
) -> None:
    with pytest.raises(EvaluationAssetConsistencyError, match=error):
        validate_evaluation_asset_bundle(bundle)


def test_rejects_version_mismatch_and_unknown_review() -> None:
    bad_case = make_case().model_copy(update={"dataset_version": "other-v1"})
    with pytest.raises(EvaluationAssetConsistencyError, match="version_mismatch"):
        validate_evaluation_asset_bundle(make_bundle(cases=(bad_case,)))

    review = make_review().model_copy(update={"case_id": "missing-case"})
    with pytest.raises(EvaluationAssetConsistencyError, match="review_unknown_case"):
        validate_evaluation_asset_bundle(make_bundle(cases=(make_case(),), reviews=(review,)))


def test_review_is_optional_unless_the_approval_gate_is_requested() -> None:
    bundle = make_bundle(cases=(make_case(),))
    validate_evaluation_asset_bundle(bundle)
    with pytest.raises(EvaluationAssetConsistencyError, match="approval_review_missing"):
        validate_evaluation_asset_bundle(bundle, require_approved_reviews=True)


def test_approval_gate_uses_latest_review_and_rejects_conflicts() -> None:
    approved = make_bundle(cases=(make_case(),), reviews=(make_review(),))
    validate_evaluation_asset_bundle(approved, require_approved_reviews=True)

    rejected = make_bundle(
        cases=(make_case(),),
        reviews=(make_review("approved", "2026-07-25"), make_review("rejected")),
    )
    with pytest.raises(EvaluationAssetConsistencyError, match="approval_not_approved"):
        validate_evaluation_asset_bundle(rejected, require_approved_reviews=True)

    conflict = make_bundle(
        cases=(make_case(),), reviews=(make_review("approved"), make_review("rejected"))
    )
    with pytest.raises(EvaluationAssetConsistencyError, match="approval_review_conflict"):
        validate_evaluation_asset_bundle(conflict, require_approved_reviews=True)


def test_empty_bundle_cannot_pass_the_approval_gate() -> None:
    with pytest.raises(EvaluationAssetConsistencyError, match="approval_gate_empty_dataset"):
        validate_evaluation_asset_bundle(make_bundle(), require_approved_reviews=True)


def test_rejects_nonstandard_json_numbers_in_fixture_match_keys() -> None:
    fixture = make_fixture().model_copy(
        update={"arguments_match": {"value": float("nan")}}
    )
    bundle = make_bundle(cases=(make_case(fixture_ids=["fixture-001"]),), fixtures=(fixture,))
    with pytest.raises(EvaluationAssetConsistencyError, match="invalid_match_arguments"):
        validate_evaluation_asset_bundle(bundle)


def test_cli_allows_an_intentionally_empty_dataset_only_with_flag(tmp_path: Path) -> None:
    script = Path(__file__).parents[2] / "scripts" / "validate_evaluation_assets.py"
    root = tmp_path / "evaluation"
    allowed = subprocess.run(
        [sys.executable, str(script), "--root", str(root), "--allow-empty"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert allowed.returncode == 0
    assert '"case_count": 0' in allowed.stdout
    assert "Synthetic" not in allowed.stdout

    rejected = subprocess.run(
        [sys.executable, str(script), "--root", str(root)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert rejected.returncode != 0
    assert "empty_dataset" in rejected.stdout


def test_bundle_is_frozen_after_construction() -> None:
    bundle = make_bundle(cases=(make_case(),))
    with pytest.raises(ValidationError):
        bundle.cases = ()  # type: ignore[misc]
