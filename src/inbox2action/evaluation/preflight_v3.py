"""Read-only formal60 asset and policy preflight for stage two."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict

from inbox2action.evaluation.asset_bundle import (
    EvaluationAssetBundleV1,
    EvaluationAssetConsistencyError,
    validate_evaluation_asset_bundle,
)
from inbox2action.evaluation.policy_v3 import (
    CaseExecutionPolicyV3,
    ParameterResolutionStatus,
)
from inbox2action.tools.policy import ALLOWED_TOOL_NAMES


class FormalPreflightResultV3(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["PASS", "FAIL"]
    case_count: int
    policy_count: int
    holdout_count: int
    development_count: int
    category_counts: dict[str, int]
    failure_reasons: list[str]


def preflight_formal_assets_v3(
    bundle: EvaluationAssetBundleV1,
    *,
    case_policies: Mapping[str, CaseExecutionPolicyV3],
    holdout_case_ids: set[str] | frozenset[str],
) -> FormalPreflightResultV3:
    reasons: list[str] = []
    try:
        validate_evaluation_asset_bundle(
            bundle,
            require_approved_reviews=True,
        )
    except EvaluationAssetConsistencyError:
        reasons.append("evaluation_asset_bundle_invalid")

    case_ids = {case.case_id for case in bundle.cases}
    policy_ids = set(case_policies)
    holdout_ids = set(holdout_case_ids)
    categories = Counter(case.category.value for case in bundle.cases)

    if len(bundle.cases) != 60:
        reasons.append("formal_case_count_not_60")
    if len(case_policies) != 60:
        reasons.append("reviewed_policy_count_not_60")
    if policy_ids != case_ids:
        reasons.append("case_policy_ids_do_not_match_cases")
    if len(holdout_ids) != 20:
        reasons.append("holdout_case_count_not_20")
    if not holdout_ids.issubset(case_ids):
        reasons.append("holdout_case_missing_from_dataset")
    if len(case_ids.difference(holdout_ids)) != 40:
        reasons.append("development_case_count_not_40")

    expected_categories = {
        "ordinary",
        "task",
        "calendar",
        "multi_action",
        "prompt_injection",
    }
    if set(categories) != expected_categories or any(
        categories[category] != 12 for category in expected_categories
    ):
        reasons.append("category_balance_not_12_each")

    for case_id, policy in case_policies.items():
        if case_id != policy.case_id:
            reasons.append("case_policy_key_mismatch")
        if not policy.eligible_for_formal_acceptance:
            reasons.append("case_policy_not_formal_eligible")
        if any(
            action.tool_name not in ALLOWED_TOOL_NAMES
            for action in policy.action_plan.actions
        ):
            reasons.append("case_policy_contains_unknown_tool")
        if any(
            resolution.status
            in {
                ParameterResolutionStatus.MISSING_REQUIRED,
                ParameterResolutionStatus.AMBIGUOUS,
                ParameterResolutionStatus.CONFLICTING,
            }
            for action in policy.action_plan.actions
            for resolution in action.parameter_resolutions
        ):
            reasons.append("case_policy_contains_unresolved_executable_action")
        if any(
            action.requires_approval
            and action.action_id not in policy.approved_action_ids
            for action in policy.action_plan.actions
        ):
            reasons.append("case_policy_missing_required_approval")

    unique_reasons = list(dict.fromkeys(reasons))
    return FormalPreflightResultV3(
        status="FAIL" if unique_reasons else "PASS",
        case_count=len(bundle.cases),
        policy_count=len(case_policies),
        holdout_count=len(holdout_ids),
        development_count=len(case_ids.difference(holdout_ids)),
        category_counts=dict(sorted(categories.items())),
        failure_reasons=unique_reasons,
    )
