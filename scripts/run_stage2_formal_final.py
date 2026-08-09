"""Execute the one-time frozen final stage-two formal60 batch."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from preflight_stage2_formal_final import (
    DEFAULT_ASSET_MANIFEST,
    DEFAULT_CANDIDATE_MANIFEST,
    DEFAULT_FORMAL_ROOT,
    EXPECTED_ASSET_MANIFEST_SHA256,
    EXPECTED_ASSET_MANIFEST_SHA256_ATTEMPT_2,
    EXPECTED_CANDIDATE_MANIFEST_SHA256,
    EXPECTED_CANDIDATE_MANIFEST_SHA256_ATTEMPT_2,
    verify_hash_manifest,
)

from inbox2action.config import Settings
from inbox2action.evaluation.asset_bundle import load_evaluation_asset_bundle
from inbox2action.evaluation.deepseek_pilot import validate_live_pilot_settings
from inbox2action.evaluation.policy_v3 import load_case_execution_policies_v3
from inbox2action.evaluation.preflight_final import preflight_formal_assets_final
from inbox2action.evaluation.report_final import (
    assess_formal_validation_final,
    render_formal_validation_evidence_final,
)
from inbox2action.evaluation.runner_final import (
    PilotEvaluationRunnerFinal,
    write_pilot_evaluation_run_final,
)
from inbox2action.llm.client import OpenAIChatClient

PROJECT_ROOT = Path(__file__).parents[1]
RESULT_PATH = (
    PROJECT_ROOT / "evaluation" / "results" / "stage2-formal-final-run.json"
)
EVIDENCE_PATH = (
    PROJECT_ROOT / "evidence" / "stage-2" / "stage2-formal-final-summary.md"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--attempt-id",
        choices=("attempt-1", "attempt-2"),
        default="attempt-1",
    )
    parser.add_argument("--live-model", action="store_true")
    parser.add_argument("--confirm-api-cost", action="store_true")
    parser.add_argument("--confirm-frozen-assets", action="store_true")
    parser.add_argument("--evaluation-root", type=Path, default=DEFAULT_FORMAL_ROOT)
    parser.add_argument(
        "--policy-file",
        type=Path,
        default=DEFAULT_FORMAL_ROOT / "policies.jsonl",
    )
    parser.add_argument(
        "--holdout-ids",
        type=Path,
        default=DEFAULT_FORMAL_ROOT / "holdout.json",
    )
    parser.add_argument(
        "--candidate-manifest",
        type=Path,
        default=DEFAULT_CANDIDATE_MANIFEST,
    )
    parser.add_argument(
        "--asset-manifest",
        type=Path,
        default=DEFAULT_ASSET_MANIFEST,
    )
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--max-retries", type=int, choices=range(4), default=1)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result_path = (
        RESULT_PATH
        if args.attempt_id == "attempt-1"
        else PROJECT_ROOT
        / "evaluation"
        / "results"
        / "stage2-formal-final-attempt-2-run.json"
    )
    evidence_path = (
        EVIDENCE_PATH
        if args.attempt_id == "attempt-1"
        else PROJECT_ROOT
        / "evidence"
        / "stage-2"
        / "stage2-formal-final-attempt-2-summary.md"
    )
    candidate_manifest_sha256 = (
        EXPECTED_CANDIDATE_MANIFEST_SHA256_ATTEMPT_2
        if args.attempt_id == "attempt-2"
        else EXPECTED_CANDIDATE_MANIFEST_SHA256
    )
    asset_manifest_sha256 = (
        EXPECTED_ASSET_MANIFEST_SHA256_ATTEMPT_2
        if args.attempt_id == "attempt-2"
        else EXPECTED_ASSET_MANIFEST_SHA256
    )
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
    if result_path.exists() or evidence_path.exists():
        print(
            "formal_run_refused: final formal result or evidence already exists",
            file=sys.stderr,
        )
        return 2
    try:
        verify_hash_manifest(
            args.candidate_manifest,
            expected_manifest_sha256=candidate_manifest_sha256,
        )
        verify_hash_manifest(
            args.asset_manifest,
            expected_manifest_sha256=asset_manifest_sha256,
        )
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
        preflight = preflight_formal_assets_final(
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
        settings = Settings().model_copy(  # type: ignore[call-arg]
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

    run = PilotEvaluationRunnerFinal(
        bundle,
        OpenAIChatClient(settings),
        case_policies=policies,
        max_tool_steps=settings.llm_max_tool_steps,
        require_approved_reviews=True,
        failure_mode="continue",
    ).run()
    decision = assess_formal_validation_final(
        run,
        holdout_case_ids=holdout_ids,
    )
    write_pilot_evaluation_run_final(
        run,
        result_path,
        project_root=PROJECT_ROOT,
    )
    evidence_path.write_text(
        render_formal_validation_evidence_final(
            decision,
            run_date=datetime.now(UTC).date(),
            model_name=settings.llm_model_name,
            thinking_mode=settings.llm_thinking_mode,
            timeout_seconds=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "decision": decision.status,
                "evidence_path": str(evidence_path.relative_to(PROJECT_ROOT)),
                "result_path": str(result_path.relative_to(PROJECT_ROOT)),
            },
            sort_keys=True,
        )
    )
    return 0 if decision.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
