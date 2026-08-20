"""Run the explicitly authorized 120-case DeepSeek Stage 10 benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from inbox2action.config import Settings
from inbox2action.evaluation.deepseek_pilot import (
    LivePilotConfigurationError,
    validate_live_pilot_settings,
)
from inbox2action.evaluation.stage10_observed import (
    render_observed_markdown,
    run_observed_benchmark,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-model", action="store_true")
    parser.add_argument("--confirm-api-cost", action="store_true")
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--failure-mode", choices=("continue",), default="continue")
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path("evaluation/results/stage10-observed.json"),
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=Path("evaluation/results/stage10-observed.md"),
    )
    return parser


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.live_model or not args.confirm_api_cost:
        print(
            "observed_benchmark_refused: both --live-model and --confirm-api-cost are required",
            file=sys.stderr,
        )
        return 2
    try:
        settings = Settings()  # type: ignore[call-arg]
        validate_live_pilot_settings(settings)
        evidence = run_observed_benchmark(
            PROJECT_ROOT / "evaluation" / "dataset-vnext",
            settings=settings,
            case_ids=args.case_id or None,
            failure_mode=args.failure_mode,
        )
        _write(
            args.json_output,
            json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        )
        _write(args.markdown_output, render_observed_markdown(evidence))
    except LivePilotConfigurationError as exc:
        print(
            f"observed_benchmark_not_configured: missing={','.join(exc.missing)}",
            file=sys.stderr,
        )
        return 2
    except (OSError, TypeError, ValueError) as exc:
        print(
            f"observed_benchmark_failed: {type(exc).__name__}: {exc}", file=sys.stderr
        )
        return 1

    print(
        json.dumps(
            {
                "status": evidence["status"],
                "quality_status": evidence["quality_status"],
                "case_count": evidence["case_count"],
                "dataset_version": evidence["dataset_version"],
                "model": evidence["model"],
                "failed_case_count": len(
                    evidence["failed_cases"]
                    if isinstance(evidence["failed_cases"], Sequence)
                    else []
                ),
                "json_output": str(args.json_output),
                "markdown_output": str(args.markdown_output),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
