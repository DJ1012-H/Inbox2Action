"""Read-only structural and satisfiability preflight for the final candidate."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict

from inbox2action.evaluation.asset_bundle import EvaluationAssetBundleV1
from inbox2action.evaluation.policy_v3 import CaseExecutionPolicyV3
from inbox2action.evaluation.preflight_v3 import preflight_formal_assets_v3
from inbox2action.evaluation.triage_final import detect_prompt_injection_final


class FormalPreflightResultFinal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["PASS", "FAIL"]
    case_count: int
    policy_count: int
    holdout_count: int
    development_count: int
    category_counts: dict[str, int]
    failure_reasons: list[str]


def preflight_formal_assets_final(
    bundle: EvaluationAssetBundleV1,
    *,
    case_policies: Mapping[str, CaseExecutionPolicyV3],
    holdout_case_ids: set[str] | frozenset[str],
    max_tool_steps: int = 6,
) -> FormalPreflightResultFinal:
    """Reject structurally valid but impossible-to-score formal candidates."""

    v3 = preflight_formal_assets_v3(
        bundle,
        case_policies=case_policies,
        holdout_case_ids=holdout_case_ids,
    )
    reasons = list(v3.failure_reasons)
    if max_tool_steps <= 0 or max_tool_steps > 20:
        reasons.append("max_tool_steps_invalid")

    for case in bundle.cases:
        policy = case_policies.get(case.case_id)
        if policy is not None:
            allowed_sequences = case.expected.allowed_tool_sequences
            if not any(
                policy.action_plan.is_valid_tool_sequence(sequence)
                for sequence in allowed_sequences
            ):
                reasons.append("case_policy_has_no_gold_compatible_sequence")
            if len(policy.action_plan.actions) > max_tool_steps:
                reasons.append("case_policy_exceeds_tool_step_limit")
        if not _valid_assertion_contract(case.expected.argument_assertions):
            reasons.append("argument_assertion_contract_invalid")

        text = f"{case.email.subject}\n{case.email.body}"
        expected_injection = case.category.value == "prompt_injection"
        if detect_prompt_injection_final(text).suspected != expected_injection:
            reasons.append("deterministic_injection_contract_mismatch")

    unique_reasons = list(dict.fromkeys(reasons))
    categories = Counter(case.category.value for case in bundle.cases)
    case_ids = {case.case_id for case in bundle.cases}
    return FormalPreflightResultFinal(
        status="FAIL" if unique_reasons else "PASS",
        case_count=len(bundle.cases),
        policy_count=len(case_policies),
        holdout_count=len(holdout_case_ids),
        development_count=len(case_ids.difference(holdout_case_ids)),
        category_counts=dict(sorted(categories.items())),
        failure_reasons=unique_reasons,
    )


def _valid_assertion_contract(value: object) -> bool:
    if isinstance(value, dict):
        if "$contains_all" in value:
            if set(value) != {"$contains_all"}:
                return False
            fragments = value["$contains_all"]
            return (
                isinstance(fragments, list)
                and bool(fragments)
                and all(
                    isinstance(fragment, str) and bool(fragment.strip())
                    for fragment in fragments
                )
            )
        return all(_valid_assertion_contract(item) for item in value.values())
    if isinstance(value, list):
        return all(_valid_assertion_contract(item) for item in value)
    return value is None or isinstance(value, str | int | float | bool)
