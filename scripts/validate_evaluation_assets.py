"""Validate formal Pilot evaluation assets without executing models or tools."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from inbox2action.evaluation.asset_bundle import (
    EvaluationAssetConsistencyError,
    load_evaluation_asset_bundle,
    validate_evaluation_asset_bundle,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("evaluation"))
    parser.add_argument("--allow-empty", action="store_true")
    parser.add_argument("--require-approved-reviews", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        bundle = load_evaluation_asset_bundle(args.root, allow_empty=args.allow_empty)
        validate_evaluation_asset_bundle(
            bundle, require_approved_reviews=args.require_approved_reviews
        )
    except (EvaluationAssetConsistencyError, OSError, ValueError) as exc:
        print(f"asset_validation_failed: {type(exc).__name__}: {exc}")
        return 1

    versions = {(case.schema_version, case.dataset_version) for case in bundle.cases}
    schema_version, dataset_version = next(iter(versions), ("1.0", "deepseek-validation-v1"))
    summary = {
        "approval_gate_status": (
            "passed" if args.require_approved_reviews else "not_requested"
        ),
        "case_count": len(bundle.cases),
        "consistency_status": "passed",
        "dataset_version": dataset_version,
        "fixture_count": len(bundle.fixtures),
        "review_count": len(bundle.reviews),
        "schema_version": schema_version,
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
