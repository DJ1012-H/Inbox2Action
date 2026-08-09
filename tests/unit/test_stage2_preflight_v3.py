from __future__ import annotations

import json
from pathlib import Path

from inbox2action.evaluation.asset_bundle import (
    EvaluationAssetBundleV1,
    load_evaluation_asset_bundle,
)
from inbox2action.evaluation.assets import EvaluationCategoryV1, ReviewRecordV1
from inbox2action.evaluation.policy_v3 import (
    ActionNodeV3,
    ActionPlanV3,
    CaseExecutionPolicyV3,
    load_case_execution_policies_v3,
)
from inbox2action.evaluation.preflight_v3 import preflight_formal_assets_v3

PROJECT_ROOT = Path(__file__).parents[2]


def _policy(case_id: str, tool_name: str = "done") -> CaseExecutionPolicyV3:
    actions = [ActionNodeV3(action_id="action-1", tool_name=tool_name)]
    if tool_name != "done":
        actions.append(
            ActionNodeV3(
                action_id="done",
                tool_name="done",
                depends_on=("action-1",),
            )
        )
    return CaseExecutionPolicyV3(
        case_id=case_id,
        review_status="approved",
        policy_source="reviewed_policy",
        action_plan=ActionPlanV3(actions=tuple(actions)),
    )


def _formal_bundle() -> EvaluationAssetBundleV1:
    source = load_evaluation_asset_bundle(PROJECT_ROOT / "evaluation")
    base_case = next(
        case for case in source.cases if case.case_id == "ordinary_advertisement_001"
    )
    base_review = next(
        review
        for review in source.reviews
        if review.case_id == "ordinary_advertisement_001"
    )
    categories = (
        EvaluationCategoryV1.ORDINARY,
        EvaluationCategoryV1.TASK,
        EvaluationCategoryV1.CALENDAR,
        EvaluationCategoryV1.MULTI_ACTION,
        EvaluationCategoryV1.PROMPT_INJECTION,
    )
    cases = tuple(
        base_case.model_copy(
            update={
                "case_id": f"formal-{index:03d}",
                "category": categories[(index - 1) // 12],
            }
        )
        for index in range(1, 61)
    )
    reviews = tuple(
        ReviewRecordV1.model_validate(
            {
                **base_review.model_dump(mode="json"),
                "case_id": case.case_id,
            }
        )
        for case in cases
    )
    return EvaluationAssetBundleV1(cases=cases, fixtures=(), reviews=reviews)


def test_current_formal_candidate_passes_preflight() -> None:
    bundle = load_evaluation_asset_bundle(PROJECT_ROOT / "evaluation")
    policies = load_case_execution_policies_v3(
        PROJECT_ROOT / "evaluation" / "policies-v3.jsonl"
    )
    holdout_ids = set(
        json.loads(
            (PROJECT_ROOT / "evaluation" / "holdout-v3.json").read_text(
                encoding="utf-8"
            )
        )
    )

    result = preflight_formal_assets_v3(
        bundle,
        case_policies=policies,
        holdout_case_ids=holdout_ids,
    )

    assert result.status == "PASS"
    assert result.case_count == 60
    assert result.policy_count == 60
    assert result.holdout_count == 20
    assert result.development_count == 40
    assert set(result.category_counts.values()) == {12}


def test_balanced_60_cases_60_reviewed_policies_and_20_holdout_pass() -> None:
    bundle = _formal_bundle()
    policies = {case.case_id: _policy(case.case_id) for case in bundle.cases}
    holdout_ids = {case.case_id for case in bundle.cases[-20:]}

    result = preflight_formal_assets_v3(
        bundle,
        case_policies=policies,
        holdout_case_ids=holdout_ids,
    )

    assert result.status == "PASS"
    assert result.case_count == 60
    assert result.policy_count == 60
    assert result.holdout_count == 20
    assert set(result.category_counts.values()) == {12}


def test_unknown_policy_tool_and_unreviewed_policy_fail_preflight() -> None:
    bundle = _formal_bundle()
    policies = {case.case_id: _policy(case.case_id) for case in bundle.cases}
    first_id = bundle.cases[0].case_id
    policies[first_id] = _policy(first_id, "execute_shell").model_copy(
        update={"review_status": "draft"}
    )

    result = preflight_formal_assets_v3(
        bundle,
        case_policies=policies,
        holdout_case_ids={case.case_id for case in bundle.cases[-20:]},
    )

    assert result.status == "FAIL"
    assert "case_policy_not_formal_eligible" in result.failure_reasons
    assert "case_policy_contains_unknown_tool" in result.failure_reasons
