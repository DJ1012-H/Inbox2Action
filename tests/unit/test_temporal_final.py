from __future__ import annotations

from pathlib import Path

from inbox2action.evaluation.asset_bundle import load_evaluation_asset_bundle
from inbox2action.evaluation.temporal_final import (
    resolve_calendar_interval_final,
    resolve_task_due_at_final,
)

PROJECT_ROOT = Path(__file__).parents[2]


def test_deterministic_temporal_resolver_matches_all_revealed_schedules() -> None:
    bundle = load_evaluation_asset_bundle(PROJECT_ROOT / "evaluation")
    checked_due = 0
    checked_intervals = 0

    for case in bundle.cases:
        task_assertion = case.expected.argument_assertions.get(
            "save_task_proposal",
            {},
        )
        expected_due = task_assertion.get("due_at")
        if isinstance(expected_due, str):
            resolved_due = resolve_task_due_at_final(case)
            assert resolved_due is not None, case.case_id
            assert resolved_due.isoformat() == expected_due, case.case_id
            checked_due += 1

        calendar_assertion = case.expected.argument_assertions.get(
            "check_calendar_availability",
            {},
        )
        expected_start = calendar_assertion.get("start")
        expected_end = calendar_assertion.get("end")
        if isinstance(expected_start, str) and isinstance(expected_end, str):
            interval = resolve_calendar_interval_final(case)
            assert interval is not None, case.case_id
            assert interval.start.isoformat() == expected_start, case.case_id
            assert interval.end.isoformat() == expected_end, case.case_id
            checked_intervals += 1

    assert checked_due == 14
    assert checked_intervals == 20
