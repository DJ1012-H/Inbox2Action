"""Write the immutable hash manifest for the final formal60 asset bundle."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from inbox2action.evaluation.asset_bundle import load_evaluation_asset_bundle
from inbox2action.evaluation.policy_v3 import load_case_execution_policies_v3
from inbox2action.evaluation.preflight_final import preflight_formal_assets_final

PROJECT_ROOT = Path(__file__).parents[1]
FORMAL_ROOT = PROJECT_ROOT / "evaluation" / "formal-final"
MANIFEST_PATH = FORMAL_ROOT / "formal-asset-manifest.json"
ASSET_PATHS = (
    "evaluation/formal-final/cases/ordinary.jsonl",
    "evaluation/formal-final/cases/task.jsonl",
    "evaluation/formal-final/cases/calendar.jsonl",
    "evaluation/formal-final/cases/multi_action.jsonl",
    "evaluation/formal-final/cases/prompt_injection.jsonl",
    "evaluation/formal-final/fixtures/tool_observations.jsonl",
    "evaluation/formal-final/reviews/review-records.jsonl",
    "evaluation/formal-final/policies.jsonl",
    "evaluation/formal-final/holdout.json",
    "evaluation/schemas-v3/stage2-action-plan-v3.schema.json",
    "evaluation/schemas-v3/stage2-case-policy-v3.schema.json",
    "evaluation/schemas-v3/stage2-formal-decision-v3.schema.json",
    "evaluation/schemas-v3/stage2-run-v3.schema.json",
    "evaluation/schemas-v3/stage2-triage-v3.schema.json",
    "scripts/build_stage2_formal_assets.py",
    "scripts/freeze_stage2_formal_assets.py",
)


def main() -> int:
    if MANIFEST_PATH.exists():
        raise SystemExit("formal_asset_freeze_refused: manifest already exists")
    bundle = load_evaluation_asset_bundle(FORMAL_ROOT)
    policies = load_case_execution_policies_v3(FORMAL_ROOT / "policies.jsonl")
    holdout_payload = json.loads(
        (FORMAL_ROOT / "holdout.json").read_text(encoding="utf-8")
    )
    if not isinstance(holdout_payload, list) or any(
        not isinstance(case_id, str) for case_id in holdout_payload
    ):
        raise ValueError("holdout IDs must be a JSON string array")
    holdout_ids = set(holdout_payload)
    preflight = preflight_formal_assets_final(
        bundle,
        case_policies=policies,
        holdout_case_ids=holdout_ids,
    )
    if preflight.status != "PASS":
        raise ValueError("formal assets do not satisfy final preflight")

    case_ids = [case.case_id for case in bundle.cases]
    development_ids = [
        case_id for case_id in case_ids if case_id not in holdout_ids
    ]
    hashes = {
        relative: hashlib.sha256((PROJECT_ROOT / relative).read_bytes()).hexdigest()
        for relative in ASSET_PATHS
    }
    payload = {
        "schema_version": "stage2-final-asset-freeze-1",
        "frozen_at": "2026-08-06",
        "candidate_version": "stage2-remediation-final",
        "case_count": len(case_ids),
        "development_count": len(development_ids),
        "holdout_count": len(holdout_payload),
        "category_counts": dict(
            sorted(Counter(case.category.value for case in bundle.cases).items())
        ),
        "case_ids": case_ids,
        "development_case_ids": development_ids,
        "holdout_case_ids": holdout_payload,
        "sha256": hashes,
    }
    MANIFEST_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "case_count": len(case_ids),
                "development_count": len(development_ids),
                "holdout_count": len(holdout_payload),
                "manifest_path": str(MANIFEST_PATH.relative_to(PROJECT_ROOT)),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
