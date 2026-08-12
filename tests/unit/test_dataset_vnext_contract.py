from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from inbox2action.evaluation.dataset_vnext import (
    CandidateReviewRecordVNext,
    CandidateReviewStatus,
    DatasetSplit,
    EmailDatasetCaseVNext,
    WorkflowScenarioType,
    lf_sha256,
    load_jsonl,
    validate_dataset_vnext,
)

PROJECT_ROOT = Path(__file__).parents[2]
DATASET_ROOT = PROJECT_ROOT / "evaluation" / "dataset-vnext"


def _load_cases(root: Path = DATASET_ROOT) -> tuple[EmailDatasetCaseVNext, ...]:
    records: list[EmailDatasetCaseVNext] = []
    for filename in (
        "development.jsonl",
        "regression.jsonl",
        "security-challenge.jsonl",
    ):
        records.extend(
            load_jsonl(
                root / "cases" / filename,
                EmailDatasetCaseVNext,
                identifier=lambda item: item.case_id,
            )
        )
    return tuple(records)


def test_checked_in_dataset_vnext_is_complete_but_not_formal() -> None:
    summary = validate_dataset_vnext(DATASET_ROOT)

    assert summary.case_count == 120
    assert summary.split_counts == {
        "development": 60,
        "regression": 30,
        "security_challenge": 30,
    }
    assert summary.language_counts == {"en": 28, "zh-CN": 70, "zh-TW": 22}
    assert summary.workflow_scenario_count == 30
    assert summary.fixture_count == 60
    assert summary.review_status_counts == {"draft": 120}
    assert set(summary.workflow_type_counts) == {
        item.value for item in WorkflowScenarioType
    }
    assert all(count == 3 for count in summary.workflow_type_counts.values())
    assert summary.formal_holdout_created is False
    assert summary.real_provider_evidence is False
    assert not (DATASET_ROOT / "formal-holdout").exists()


def test_dataset_vnext_rebuild_is_deterministic(tmp_path: Path) -> None:
    script = PROJECT_ROOT / "scripts" / "build_dataset_vnext.py"
    rebuilt = tmp_path / "dataset-vnext"
    completed = subprocess.run(
        [sys.executable, str(script), "--output-root", str(rebuilt)],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert '"status": "PASS"' in completed.stdout
    manifest = json.loads((DATASET_ROOT / "manifest.json").read_text(encoding="utf-8"))
    relative_paths = ["manifest.json", *manifest["asset_sha256"]]
    for relative_path in relative_paths:
        assert (rebuilt / relative_path).read_bytes() == (
            DATASET_ROOT / relative_path
        ).read_bytes()


def test_dataset_vnext_uses_synthetic_sources_and_draft_reviews() -> None:
    cases = _load_cases()
    reviews = load_jsonl(
        DATASET_ROOT / "reviews" / "review-records.jsonl",
        CandidateReviewRecordVNext,
        identifier=lambda item: item.case_id,
    )

    assert len({item.case_id for item in cases}) == 120
    assert len({item.envelope.subject for item in cases}) == 120
    assert len({item.envelope.body for item in cases}) == 120
    assert all(
        item.envelope.from_address.endswith(("@example.com", "@example.test"))
        for item in cases
    )
    assert all(
        attachment.synthetic_only
        for item in cases
        for attachment in item.envelope.attachments
    )
    assert all(item.status is CandidateReviewStatus.DRAFT for item in reviews)
    assert all(item.reviewed_at is None for item in reviews)
    assert {item.split for item in cases} == set(DatasetSplit)
    assert not any("holdout" in item.case_id.casefold() for item in cases)


def test_dataset_vnext_covers_extended_email_and_fail_closed_paths() -> None:
    cases = _load_cases()
    tags = {tag for item in cases for tag in item.tags}

    assert sum(item.envelope.html is not None for item in cases) == 27
    assert sum(bool(item.envelope.attachments) for item in cases) == 21
    assert sum(item.envelope.provider_thread_id is not None for item in cases) == 27
    assert sum(item.expected.normalization.expect_truncated for item in cases) == 12
    assert sum(item.expected.normalization.minimum_redactions > 0 for item in cases) == 30
    assert sum(
        item.expected.normalization.minimum_tracking_parameters_removed > 0
        for item in cases
    ) == 30
    assert {
        "duplicate_delivery",
        "approval_edit",
        "stale_approval",
        "restart_recovery",
        "provider_failure",
        "provider_unknown",
        "payload_hash_mismatch",
        "dependency_order",
        "rejection",
        "retry_after_failure",
    }.issubset(tags)
    assert all(item.expected.maximum_external_side_effects == 0 for item in cases)
    assert all(item.expected.maximum_unauthorized_writes == 0 for item in cases)
    assert all(item.expected.maximum_approval_bypasses == 0 for item in cases)


def test_lf_hash_is_portable_across_windows_line_endings(tmp_path: Path) -> None:
    source = DATASET_ROOT / "reviews" / "review-records.jsonl"
    crlf_copy = tmp_path / "review-records.jsonl"
    crlf_copy.write_text(
        source.read_text(encoding="utf-8").replace("\n", "\r\n"),
        encoding="utf-8",
        newline="",
    )

    assert lf_sha256(crlf_copy) == lf_sha256(source)


def test_vnext_schemas_use_json_schema_2020_12() -> None:
    schema_paths = sorted((DATASET_ROOT / "schemas").glob("*.schema.json"))

    assert len(schema_paths) == 4
    for path in schema_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert payload["title"]
