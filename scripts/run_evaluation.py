from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from inbox2action.config import Settings
from inbox2action.evaluation.report import render_stage_two_report
from inbox2action.evaluation.runner import (
    dry_run,
    live_run,
    select_cases,
    write_run_json,
)
from inbox2action.evaluation.schema import EvaluationCategory, load_jsonl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the safe stage-two evaluator.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Do not call a model.")
    mode.add_argument(
        "--live-model",
        action="store_true",
        help="Explicitly opt in to model calls using the configured DeepSeek client.",
    )
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument("--case-id")
    parser.add_argument(
        "--category", choices=[item.value for item in EvaluationCategory]
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/results/checkpoint-3-run.json"),
    )
    parser.add_argument("--failure-mode", choices=["stop", "continue"], default="stop")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path("evaluation/fixtures/checkpoint-3-sample.jsonl"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("docs/stage-2/model-validation-report.md"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path.cwd().resolve()
    try:
        dataset = load_jsonl(args.fixture)
        cases = select_cases(
            dataset,
            limit=args.limit,
            case_id=args.case_id,
            category=args.category,
        )
        if args.live_model:
            settings = Settings()
            if not (
                settings.run_deepseek_integration_tests
                and settings.llm_enabled
                and settings.api_key_configured
            ):
                print(
                    "live-model requires explicit integration opt-in, enabled LLM, and a configured key.",
                    file=sys.stderr,
                )
                return 2
            run = live_run(cases, settings, failure_mode=args.failure_mode)
        else:
            settings = Settings()
            run = dry_run(cases)
        write_run_json(run, args.output, project_root=project_root)
        report_path = args.report.resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            render_stage_two_report(dataset, run, settings),
            encoding="utf-8",
        )
    except (OSError, ValueError, ValidationError) as exc:
        print(f"evaluation_error={type(exc).__name__}", file=sys.stderr)
        return 2
    print(f"mode={run.mode} cases={len(run.results)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
