"""Run one explicitly authorized, five-case DeepSeek Pilot baseline."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import ValidationError

from inbox2action.config import Settings
from inbox2action.evaluation.asset_bundle import (
    EvaluationAssetConsistencyError,
    load_evaluation_asset_bundle,
    validate_evaluation_asset_bundle,
)
from inbox2action.evaluation.deepseek_pilot import (
    LivePilotConfigurationError,
    LivePilotRequestError,
    redacted_pilot_summary,
    render_deepseek_pilot_summary,
    validate_live_pilot_request,
    validate_live_pilot_settings,
)
from inbox2action.evaluation.runner_v1 import (
    PilotEvaluationRunnerV1,
    PilotEvaluationRunV1,
    write_pilot_evaluation_run,
)
from inbox2action.llm.client import OpenAIChatClient

PROJECT_ROOT = Path(__file__).parents[1]
RESULT_PATH = PROJECT_ROOT / "evaluation" / "results" / "deepseek-pilot-v1-run.json"
EVIDENCE_PATH = PROJECT_ROOT / "evidence" / "stage-2" / "deepseek-pilot-v1-summary.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-model", action="store_true")
    parser.add_argument("--confirm-api-cost", action="store_true")
    parser.add_argument(
        "--render-existing-result",
        action="store_true",
        help="Regenerate only the redacted evidence from the existing result file.",
    )
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--failure-mode", choices=("continue",), default="continue")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.render_existing_result:
        return _render_existing_result()
    try:
        case_ids = validate_live_pilot_request(
            live_model=args.live_model,
            confirm_api_cost=args.confirm_api_cost,
            case_ids=args.case_id,
            failure_mode=args.failure_mode,
        )
        bundle = load_evaluation_asset_bundle(PROJECT_ROOT / "evaluation")
        validate_evaluation_asset_bundle(bundle, require_approved_reviews=True)
        _validate_selected_case_ids(
            tuple(case.case_id for case in bundle.cases), case_ids
        )
        settings = Settings()
        validate_live_pilot_settings(settings)
    except LivePilotRequestError as exc:
        print(f"deepseek_pilot_refused: {exc}", file=sys.stderr)
        return 2
    except LivePilotConfigurationError as exc:
        print(
            f"deepseek_pilot_not_configured: missing={','.join(exc.missing)}",
            file=sys.stderr,
        )
        return 2
    except (EvaluationAssetConsistencyError, OSError, ValidationError, ValueError) as exc:
        print(f"deepseek_pilot_preflight_failed: {type(exc).__name__}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "base_url_hostname": urlsplit(settings.llm_base_url).hostname,
                "case_ids": list(case_ids),
                "model": settings.llm_model_name,
                "prompt_version": "pilot-evaluation-v1",
                "thinking_mode": settings.llm_thinking_mode,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    try:
        run = PilotEvaluationRunnerV1(
            bundle,
            OpenAIChatClient(settings),
            max_tool_steps=settings.llm_max_tool_steps,
            require_approved_reviews=True,
            failure_mode="continue",
        ).run(case_ids=case_ids)
        write_pilot_evaluation_run(run, RESULT_PATH, project_root=PROJECT_ROOT)
        EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE_PATH.write_text(
            render_deepseek_pilot_summary(
                run,
                settings,
                run_date=datetime.now(UTC).date(),
            ),
            encoding="utf-8",
        )
    except (OSError, ValueError) as exc:
        print(f"deepseek_pilot_execution_failed: {type(exc).__name__}", file=sys.stderr)
        return 1

    print(json.dumps(redacted_pilot_summary(run), ensure_ascii=False, sort_keys=True))
    return 0


def _render_existing_result() -> int:
    """Write only redacted evidence from the persisted result; never build a client."""

    try:
        run = PilotEvaluationRunV1.model_validate_json(
            RESULT_PATH.read_text(encoding="utf-8")
        )
        settings = Settings()
        EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE_PATH.write_text(
            render_deepseek_pilot_summary(
                run,
                settings,
                run_date=datetime.now(UTC).date(),
            ),
            encoding="utf-8",
        )
    except (OSError, ValidationError, ValueError) as exc:
        print(f"deepseek_pilot_render_failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(json.dumps(redacted_pilot_summary(run), ensure_ascii=False, sort_keys=True))
    return 0


def _validate_selected_case_ids(
    available_case_ids: tuple[str, ...], case_ids: tuple[str, ...]
) -> None:
    """Fail before client construction if a requested case is absent from the bundle."""

    if not set(case_ids).issubset(available_case_ids):
        raise ValueError("requested case_id is absent from the formal asset bundle")


if __name__ == "__main__":
    raise SystemExit(main())
