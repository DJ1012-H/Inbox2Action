from __future__ import annotations

import json
from pathlib import Path

import pytest

from inbox2action.evaluation.policy_v3 import (
    ActionNodeV3,
    ActionPlanV3,
    CaseExecutionPolicyV3,
    load_case_execution_policies_v3,
)


def _policy(case_id: str) -> CaseExecutionPolicyV3:
    return CaseExecutionPolicyV3(
        case_id=case_id,
        review_status="approved",
        policy_source="reviewed_policy",
        action_plan=ActionPlanV3(
            actions=(ActionNodeV3(action_id="done", tool_name="done"),)
        ),
    )


def test_policy_loader_reads_strict_jsonl_and_preserves_case_ids(
    tmp_path: Path,
) -> None:
    path = tmp_path / "policies.jsonl"
    records = [_policy("case-001"), _policy("case-002")]
    path.write_text(
        "".join(
            json.dumps(record.model_dump(mode="json")) + "\n" for record in records
        ),
        encoding="utf-8",
    )

    loaded = load_case_execution_policies_v3(path)

    assert tuple(loaded) == ("case-001", "case-002")
    assert all(policy.eligible_for_formal_acceptance for policy in loaded.values())


def test_policy_loader_rejects_duplicates_without_leaking_record_content(
    tmp_path: Path,
) -> None:
    path = tmp_path / "policies.jsonl"
    record = _policy("case-001")
    serialized = json.dumps(record.model_dump(mode="json"))
    path.write_text(f"{serialized}\n{serialized}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate case policy") as captured:
        load_case_execution_policies_v3(path)

    assert serialized not in str(captured.value)


def test_policy_loader_rejects_more_than_60_records(tmp_path: Path) -> None:
    path = tmp_path / "policies.jsonl"
    path.write_text(
        "".join(
            json.dumps(_policy(f"case-{index:03d}").model_dump(mode="json")) + "\n"
            for index in range(1, 62)
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="too many case policies"):
        load_case_execution_policies_v3(path)
