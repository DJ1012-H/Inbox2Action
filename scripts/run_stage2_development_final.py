"""Run one numbered diagnostic for the single converged final candidate."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from inbox2action.config import Settings
from inbox2action.evaluation.asset_bundle import load_evaluation_asset_bundle
from inbox2action.evaluation.deepseek_pilot import validate_live_pilot_settings
from inbox2action.evaluation.policy_v3 import load_case_execution_policies_v3
from inbox2action.evaluation.preflight_v3 import preflight_formal_assets_v3
from inbox2action.evaluation.report_final import (
    assess_development_diagnostic_final,
    render_development_diagnostic_final,
)
from inbox2action.evaluation.runner_final import (
    PilotEvaluationRunnerFinal,
    write_pilot_evaluation_run_final,
)
from inbox2action.llm.client import OpenAIChatClient

PROJECT_ROOT = Path(__file__).parents[1]
_RUN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--live-model", action="store_true")
    parser.add_argument("--confirm-api-cost", action="store_true")
    parser.add_argument("--confirm-revealed-development-data", action="store_true")
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
        "--revealed-split",
        type=Path,
        default=PROJECT_ROOT / "evaluation" / "holdout-v3.json",
    )
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--max-retries", type=int, choices=range(4), default=1)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not _RUN_ID_PATTERN.fullmatch(args.run_id):
        print("development_run_refused: invalid run ID", file=sys.stderr)
        return 2
    if not (
        args.live_model
        and args.confirm_api_cost
        and args.confirm_revealed_development_data
    ):
        print(
            "development_run_refused: --live-model, --confirm-api-cost, and "
            "--confirm-revealed-development-data are all required",
            file=sys.stderr,
        )
        return 2
    result_path = (
        PROJECT_ROOT
        / "evaluation"
        / "results"
        / f"stage2-development-final-{args.run_id}.json"
    )
    evidence_path = (
        PROJECT_ROOT
        / "evidence"
        / "stage-2"
        / f"stage2-development-final-{args.run_id}.md"
    )
    if result_path.exists() or evidence_path.exists():
        print(
            "development_run_refused: final diagnostic output already exists",
            file=sys.stderr,
        )
        return 2
    try:
        bundle = load_evaluation_asset_bundle(args.evaluation_root)
        policies = load_case_execution_policies_v3(args.policy_file)
        split_payload = json.loads(args.revealed_split.read_text(encoding="utf-8"))
        if not isinstance(split_payload, list) or any(
            not isinstance(case_id, str) for case_id in split_payload
        ):
            raise ValueError("revealed split must be a JSON string array")
        preflight = preflight_formal_assets_v3(
            bundle,
            case_policies=policies,
            holdout_case_ids=set(split_payload),
        )
        if preflight.status != "PASS":
            print(
                "development_run_refused: "
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
            f"development_run_refused: {type(exc).__name__}",
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
    diagnostic = assess_development_diagnostic_final(run)
    write_pilot_evaluation_run_final(
        run,
        result_path,
        project_root=PROJECT_ROOT,
    )
    evidence_path.write_text(
        render_development_diagnostic_final(
            diagnostic,
            run_id=args.run_id,
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
                "candidate_readiness": diagnostic.status,
                "evidence_path": str(evidence_path.relative_to(PROJECT_ROOT)),
                "result_path": str(result_path.relative_to(PROJECT_ROOT)),
            },
            sort_keys=True,
        )
    )
    return 0 if diagnostic.status == "READY_FOR_FREEZE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
