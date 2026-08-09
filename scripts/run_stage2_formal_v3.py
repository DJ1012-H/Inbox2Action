"""Execute the one-time policy-gated stage-two formal60 batch."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from inbox2action.config import Settings
from inbox2action.evaluation.asset_bundle import load_evaluation_asset_bundle
from inbox2action.evaluation.deepseek_pilot import validate_live_pilot_settings
from inbox2action.evaluation.policy_v3 import load_case_execution_policies_v3
from inbox2action.evaluation.preflight_v3 import preflight_formal_assets_v3
from inbox2action.evaluation.report_v3 import (
    assess_formal_validation_v3,
    render_formal_validation_evidence_v3,
)
from inbox2action.evaluation.runner_v3 import (
    PilotEvaluationRunnerV3,
    write_pilot_evaluation_run_v3,
)
from inbox2action.llm.client import OpenAIChatClient

PROJECT_ROOT = Path(__file__).parents[1]
RESULT_PATH = (
    PROJECT_ROOT / "evaluation" / "results" / "stage2-formal-v3-run.json"
)
EVIDENCE_PATH = (
    PROJECT_ROOT / "evidence" / "stage-2" / "stage2-formal-v3-summary.md"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-model", action="store_true")
    parser.add_argument("--confirm-api-cost", action="store_true")
    parser.add_argument("--confirm-frozen-assets", action="store_true")
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
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--max-retries", type=int, choices=range(4), default=1)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not (
        args.live_model
        and args.confirm_api_cost
        and args.confirm_frozen_assets
    ):
        print(
            "formal_run_refused: --live-model, --confirm-api-cost, and "
            "--confirm-frozen-assets are all required",
            file=sys.stderr,
        )
        return 2
    if RESULT_PATH.exists() or EVIDENCE_PATH.exists():
        print(
            "formal_run_refused: formal v3 result or evidence already exists",
            file=sys.stderr,
        )
        return 2
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
        holdout_ids = set(holdout_payload)
        preflight = preflight_formal_assets_v3(
            bundle,
            case_policies=policies,
            holdout_case_ids=holdout_ids,
        )
        if preflight.status != "PASS":
            print(
                "formal_run_refused: "
                + json.dumps(preflight.model_dump(mode="json"), sort_keys=True),
                file=sys.stderr,
            )
            return 2
        settings = Settings().model_copy(
            update={
                "llm_timeout_seconds": args.timeout_seconds,
                "llm_max_retries": args.max_retries,
            }
        )
        validate_live_pilot_settings(settings)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(
            f"formal_run_refused: {type(exc).__name__}",
            file=sys.stderr,
        )
        return 2

    runner = PilotEvaluationRunnerV3(
        bundle,
        OpenAIChatClient(settings),
        case_policies=policies,
        max_tool_steps=settings.llm_max_tool_steps,
        require_approved_reviews=True,
        failure_mode="continue",
    )
    run = runner.run()
    decision = assess_formal_validation_v3(
        run,
        holdout_case_ids=holdout_ids,
    )
    write_pilot_evaluation_run_v3(
        run,
        RESULT_PATH,
        project_root=PROJECT_ROOT,
    )
    evidence = render_formal_validation_evidence_v3(
        decision,
        run_date=datetime.now(UTC).date(),
        model_name=settings.llm_model_name,
        thinking_mode=settings.llm_thinking_mode,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
    EVIDENCE_PATH.write_text(evidence, encoding="utf-8")
    print(
        json.dumps(
            {
                "decision": decision.status,
                "evidence_path": str(EVIDENCE_PATH.relative_to(PROJECT_ROOT)),
                "result_path": str(RESULT_PATH.relative_to(PROJECT_ROOT)),
            },
            sort_keys=True,
        )
    )
    return 0 if decision.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
