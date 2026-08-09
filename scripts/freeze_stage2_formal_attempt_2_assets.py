"""Freeze hashes and IDs for the second independent formal60 asset bundle."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from inbox2action.evaluation.asset_bundle import load_evaluation_asset_bundle
from inbox2action.evaluation.policy_v3 import load_case_execution_policies_v3
from inbox2action.evaluation.preflight_final import preflight_formal_assets_final

PROJECT_ROOT = Path(__file__).parents[1]
FORMAL_ROOT = PROJECT_ROOT / "evaluation" / "formal-final-attempt-2"
MANIFEST_PATH = FORMAL_ROOT / "formal-asset-manifest.json"
ASSET_PATHS = (
    "evaluation/formal-final-attempt-2/cases/ordinary.jsonl",
    "evaluation/formal-final-attempt-2/cases/task.jsonl",
    "evaluation/formal-final-attempt-2/cases/calendar.jsonl",
    "evaluation/formal-final-attempt-2/cases/multi_action.jsonl",
    "evaluation/formal-final-attempt-2/cases/prompt_injection.jsonl",
    "evaluation/formal-final-attempt-2/fixtures/tool_observations.jsonl",
    "evaluation/formal-final-attempt-2/reviews/review-records.jsonl",
    "evaluation/formal-final-attempt-2/policies.jsonl",
    "evaluation/formal-final-attempt-2/holdout.json",
    "evaluation/schemas-v3/stage2-action-plan-v3.schema.json",
    "evaluation/schemas-v3/stage2-case-policy-v3.schema.json",
    "evaluation/schemas-v3/stage2-formal-decision-v3.schema.json",
    "evaluation/schemas-v3/stage2-run-v3.schema.json",
    "evaluation/schemas-v3/stage2-triage-v3.schema.json",
    "scripts/build_stage2_formal_attempt_2_assets.py",
    "scripts/freeze_stage2_formal_attempt_2_assets.py",
)


def main() -> int:
    if MANIFEST_PATH.exists():
        raise SystemExit("formal_asset_freeze_refused: manifest already exists")
    bundle = load_evaluation_asset_bundle(FORMAL_ROOT)
    policies = load_case_execution_policies_v3(FORMAL_ROOT / "policies.jsonl")
    holdout = json.loads(
        (FORMAL_ROOT / "holdout.json").read_text(encoding="utf-8")
    )
    if not isinstance(holdout, list) or any(
        not isinstance(case_id, str) for case_id in holdout
    ):
        raise ValueError("holdout IDs must be a JSON string array")
    preflight = preflight_formal_assets_final(
        bundle,
        case_policies=policies,
        holdout_case_ids=set(holdout),
    )
    if preflight.status != "PASS":
        raise ValueError(
            "final preflight failed: " + ",".join(preflight.failure_reasons)
        )
    case_ids = [case.case_id for case in bundle.cases]
    holdout_ids = set(holdout)
    development_ids = [
        case_id for case_id in case_ids if case_id not in holdout_ids
    ]
    payload = {
        "schema_version": "stage2-final-asset-freeze-1",
        "frozen_at": "2026-08-06",
        "formal_attempt": "attempt-2",
        "candidate_version": "stage2-remediation-final",
        "candidate_manifest": (
            "evaluation/final-candidate-freeze-after-formal-fail.json"
        ),
        "candidate_manifest_sha256": (
            "e9961c181fad62bd84a4c8dd2764c5847e18e07d20e44fa7c23b8303efd34a58"
        ),
        "case_count": len(case_ids),
        "development_count": len(development_ids),
        "holdout_count": len(holdout),
        "category_counts": dict(
            sorted(Counter(case.category.value for case in bundle.cases).items())
        ),
        "case_ids": case_ids,
        "development_case_ids": development_ids,
        "holdout_case_ids": holdout,
        "sha256": {
            relative: hashlib.sha256(
                (PROJECT_ROOT / relative).read_bytes()
            ).hexdigest()
            for relative in ASSET_PATHS
        },
    }
    MANIFEST_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(preflight.model_dump(mode="json"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
