from __future__ import annotations

import json
from pathlib import Path

from inbox2action.evaluation.dataset_vnext import (
    CandidateReviewRecordVNext,
    EmailDatasetCaseVNext,
)
from inbox2action.evaluation.stage10 import (
    audit_dataset,
    classification_metrics,
    critical_argument_metrics,
    run_checkpoint_regression,
    run_idempotency_regression,
    run_memory_regression,
    run_security_regression_suite,
    run_stage10_report,
    security_metrics,
    temporal_metrics,
    tool_selection_metrics,
    trajectory_metrics,
)

PROJECT_ROOT = Path(__file__).parents[2]
DATASET_ROOT = PROJECT_ROOT / "evaluation" / "dataset-vnext"


def _first_case() -> EmailDatasetCaseVNext:
    line = (DATASET_ROOT / "cases" / "development.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()[0]
    return EmailDatasetCaseVNext.model_validate(json.loads(line))


def _write_one_case(root: Path, *, approved: bool = False) -> None:
    case = _first_case()
    cases = root / "cases"
    reviews = root / "reviews"
    cases.mkdir(parents=True)
    reviews.mkdir()
    (cases / "development.jsonl").write_text(
        json.dumps(case.model_dump(mode="json"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    review = CandidateReviewRecordVNext(
        case_id=case.case_id,
        reviewer="human-reviewer",
        reviewed_at="2026-08-20" if approved else None,
        status="approved" if approved else "draft",
        notes="reviewed" if approved else "pending",
    )
    (reviews / "review-records.jsonl").write_text(
        json.dumps(review.model_dump(mode="json"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def test_canonical_audit_is_deterministic_and_uses_historical_provenance() -> None:
    first = audit_dataset(DATASET_ROOT)
    second = audit_dataset(DATASET_ROOT)

    assert first.dataset_case_count == 120
    assert first.total_cases == 120
    assert first.approved_cases == 120
    assert first.unapproved_cases == 0
    assert first.status == "PASS"
    assert first.canonical_benchmark_ready is True
    assert first.approval_provenance["status"] == "verified"
    assert first.approval_provenance["record_count"] == 6
    assert first.approval_provenance["ignored_non_email_receipts"] == 7
    assert first.dataset_version == second.dataset_version
    assert first.triage == {"ACTION_REQUIRED": 45, "IGNORE": 15, "NOTIFY": 60}
    assert first.security == {"benign": 75, "prompt_injection": 45}
    assert first.duplicate_case_ids == ()
    assert first.missing_ground_truth == ()


def test_audit_records_duplicates_and_invalid_schema_without_rewriting(tmp_path: Path) -> None:
    _write_one_case(tmp_path, approved=True)
    source = (tmp_path / "cases" / "development.jsonl").read_text(encoding="utf-8")
    (tmp_path / "cases" / "regression.jsonl").write_text(source, encoding="utf-8")
    result = audit_dataset(tmp_path)

    assert result.duplicate_case_ids == ("vnext_dev_ordinary_001",)
    assert result.status == "FAIL"
    assert "duplicate_case_id" in result.reasons
    assert result.approved_cases == 1


def test_classification_metrics_include_exact_confusion_matrix() -> None:
    result = classification_metrics(
        ["IGNORE", "NOTIFY", "ACTION_REQUIRED", "ACTION_REQUIRED"],
        ["IGNORE", "ACTION_REQUIRED", "ACTION_REQUIRED", "NOTIFY"],
    )

    assert result["accuracy"] == 0.5
    assert result["confusion_matrix"]["NOTIFY"]["ACTION_REQUIRED"] == 1
    assert result["confusion_matrix"]["ACTION_REQUIRED"]["NOTIFY"] == 1
    assert len(result["failures"]) == 2


def test_tool_and_argument_evaluators_are_not_containment_checks() -> None:
    tools = tool_selection_metrics(
        [
            {
                "case_id": "task-only",
                "expected_tools": ["task"],
                "actual_tools": ["task", "calendar"],
                "forbidden_tools": ["calendar"],
            }
        ]
    )
    arguments = critical_argument_metrics(
        [
            {
                "case_id": "task-arguments",
                "expected_arguments": {"priority": "low", "title": "Review inbox"},
                "actual_arguments": {"priority": "high", "title": "Review inbox today"},
            }
        ]
    )

    assert tools["exact_match"] == 0.0
    assert tools["forbidden_tool_count"] == 1
    assert arguments["matched_fields"] == 1
    assert arguments["accuracy"] == 0.5


def test_trajectory_temporal_and_security_evaluators_fail_closed() -> None:
    trajectory = trajectory_metrics(
        [
            {
                "case_id": "calendar-conflict",
                "requires_observation": True,
                "requires_replan": True,
                "forbidden_tools": ["send_email"],
                "events": [
                    {"kind": "tool_call", "tool_name": "check_calendar_availability"},
                    {"kind": "observation", "status": "conflict"},
                    {"kind": "replan"},
                    {"kind": "approval"},
                    {"kind": "proposal", "tool_name": "save_calendar_proposal"},
                ],
            }
        ]
    )
    temporal = temporal_metrics(
        [
            {
                "case_id": "timezone-precedence",
                "expected": {"timezone": "Asia/Shanghai"},
                "actual": {"timezone": "Asia/Taipei"},
                "trusted_timezone": "Asia/Shanghai",
                "memory_timezone": "Asia/Taipei",
                "reference_time": "2026-08-20T09:00:00+08:00",
            }
        ]
    )
    security = security_metrics(
        [
            {
                "case_id": "injection",
                "actual_tools": ["save_task_proposal"],
                "forbidden_tools": ["save_task_proposal"],
                "hitl_bypassed": True,
            }
        ]
    )

    assert trajectory["accuracy"] == 1.0
    assert temporal["accuracy"] == 0.0
    assert security["hard_gate_passed"] is False
    assert security["security_violations"] == 1


def test_existing_production_boundaries_pass_deterministic_regressions() -> None:
    assert run_security_regression_suite()["hard_gate_passed"] is True
    assert run_checkpoint_regression()["hard_gate_passed"] is True
    assert run_idempotency_regression()["hard_gate_passed"] is True
    assert run_memory_regression()["hard_gate_passed"] is True


def test_full_report_remains_incomplete_for_unmeasured_live_gates_and_has_no_provider_write() -> None:
    report = run_stage10_report(DATASET_ROOT, mode="full")

    assert report["final_verdict"] == "INCOMPLETE"
    assert report["dataset"]["approved_cases"] == 120
    assert report["dataset"]["unapproved_cases"] == 0
    assert report["dataset"]["approval_provenance"]["status"] == "verified"
    assert report["quality"]["status"] == "UNMEASURED"
    assert report["idempotency"]["provider_post_count"] == 0
    assert "implementation complete" not in json.dumps(report, ensure_ascii=False).lower()
