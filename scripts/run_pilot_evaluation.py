"""Run only the safe offline dry-run path for the formal Pilot v1 evaluator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from inbox2action.evaluation.asset_bundle import load_evaluation_asset_bundle
from inbox2action.evaluation.runner_v1 import (
    PilotEvaluationRunnerV1,
    write_pilot_evaluation_run,
)

PROJECT_ROOT = Path(__file__).parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("evaluation"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-empty", action="store_true")
    parser.add_argument("--require-approved-reviews", action="store_true")
    parser.add_argument("--case-id", action="append")
    parser.add_argument("--category", action="append")
    parser.add_argument("--failure-mode", choices=("stop", "continue"), default="stop")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.dry_run:
        print("live model execution is not enabled by this command")
        return 2
    try:
        bundle = load_evaluation_asset_bundle(args.root, allow_empty=args.allow_empty)
        runner = PilotEvaluationRunnerV1(
            bundle,
            require_approved_reviews=args.require_approved_reviews,
            failure_mode=args.failure_mode,
        )
        run = runner.dry_run(case_ids=args.case_id, categories=args.category)
        if args.output is not None:
            write_pilot_evaluation_run(run, args.output, project_root=PROJECT_ROOT)
    except (OSError, ValueError) as exc:
        print(f"pilot_evaluation_failed: {type(exc).__name__}: {exc}")
        return 1
    print(
        json.dumps(
            {
                "case_count": len(run.results),
                "mode": run.mode,
                "prompt_version": run.prompt_version,
                "status": "planned",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
