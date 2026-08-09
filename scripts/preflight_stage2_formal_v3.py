"""Read-only preflight for the frozen stage-two formal60 candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from inbox2action.evaluation.asset_bundle import load_evaluation_asset_bundle
from inbox2action.evaluation.policy_v3 import load_case_execution_policies_v3
from inbox2action.evaluation.preflight_v3 import preflight_formal_assets_v3

PROJECT_ROOT = Path(__file__).parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evaluation-root",
        type=Path,
        default=PROJECT_ROOT / "evaluation",
    )
    parser.add_argument(
        "--policy-file",
        type=Path,
        default=PROJECT_ROOT / "evaluation" / "policies-v3.jsonl",
    )
    parser.add_argument(
        "--holdout-ids",
        type=Path,
        default=PROJECT_ROOT / "evaluation" / "holdout-v3.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        bundle = load_evaluation_asset_bundle(args.evaluation_root)
        policies = load_case_execution_policies_v3(args.policy_file)
        holdout_payload = json.loads(args.holdout_ids.read_text(encoding="utf-8"))
        if not isinstance(holdout_payload, list) or any(
            not isinstance(case_id, str) for case_id in holdout_payload
        ):
            raise ValueError("holdout IDs must be a JSON string array")
        if len(holdout_payload) != len(set(holdout_payload)):
            raise ValueError("holdout IDs must be unique")
        result = preflight_formal_assets_v3(
            bundle,
            case_policies=policies,
            holdout_case_ids=set(holdout_payload),
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "error_class": type(exc).__name__,
                    "failure_reasons": ["formal_preflight_input_invalid"],
                },
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result.model_dump(mode="json"), sort_keys=True))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
