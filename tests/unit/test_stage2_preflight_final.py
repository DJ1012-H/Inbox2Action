from __future__ import annotations

import json
from pathlib import Path

from inbox2action.evaluation.asset_bundle import load_evaluation_asset_bundle
from inbox2action.evaluation.policy_v3 import load_case_execution_policies_v3
from inbox2action.evaluation.preflight_final import preflight_formal_assets_final

PROJECT_ROOT = Path(__file__).parents[2]


def test_final_preflight_rejects_revealed_unsatisfiable_assertions() -> None:
    bundle = load_evaluation_asset_bundle(PROJECT_ROOT / "evaluation")
    policies = load_case_execution_policies_v3(
        PROJECT_ROOT / "evaluation" / "policies-v3.jsonl"
    )
    holdout = set(
        json.loads(
            (PROJECT_ROOT / "evaluation" / "holdout-v3.json").read_text(
                encoding="utf-8"
            )
        )
    )

    result = preflight_formal_assets_final(
        bundle,
        case_policies=policies,
        holdout_case_ids=holdout,
    )

    assert result.status == "FAIL"
    assert result.failure_reasons == ["argument_assertion_contract_invalid"]
