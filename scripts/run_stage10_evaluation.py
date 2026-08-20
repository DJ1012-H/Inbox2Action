"""Run the offline Stage 10 audit and regression report.

The default mode is full offline evaluation.  It never enables a model, reads
credentials, or writes to ClickUp/Calendar.  ``--live-llm`` is an explicit
metadata mode only; a separate authorized DeepSeek run must provide observed
results before it can be reported as measured.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from inbox2action.evaluation.stage10 import render_stage10_markdown, run_stage10_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--dataset-audit", action="store_true")
    modes.add_argument("--offline", action="store_true")
    modes.add_argument("--live-llm", action="store_true")
    modes.add_argument("--security", action="store_true")
    modes.add_argument("--memory", action="store_true")
    modes.add_argument("--full", action="store_true")
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=Path("evaluation/dataset-vnext"),
        help="Canonical reviewed corpus root.",
    )
    parser.add_argument(
        "--json-output",
        "--output",
        dest="json_output",
        type=Path,
        default=Path("evaluation/results/stage10-report.json"),
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=Path("evaluation/results/stage10-report.md"),
    )
    parser.add_argument(
        "--postgres-evidence",
        type=Path,
        help="Measured JSON from the opt-in PostgreSQL restart validator.",
    )
    parser.add_argument(
        "--observed-evidence",
        type=Path,
        help="Measured JSON from the authorized DeepSeek Stage 10 observed benchmark.",
    )
    parser.add_argument(
        "--run-full-pytest",
        action="store_true",
        help="Run the complete offline pytest collection before reporting it.",
    )
    return parser


def _mode(args: argparse.Namespace) -> str:
    for flag, value in (
        (args.dataset_audit, "dataset-audit"),
        (args.offline, "offline"),
        (args.live_llm, "live-llm"),
        (args.security, "security"),
        (args.memory, "memory"),
        (args.full, "full"),
    ):
        if flag:
            return value
    return "full"


def _write_report(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        postgres_evidence = None
        if args.postgres_evidence is not None:
            value = json.loads(args.postgres_evidence.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise TypeError("PostgreSQL evidence must be a JSON object")
            postgres_evidence = value
        observed_evidence = None
        if args.observed_evidence is not None:
            value = json.loads(args.observed_evidence.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise TypeError("observed benchmark evidence must be a JSON object")
            observed_evidence = value
        test_evidence = None
        if args.run_full_pytest:
            with tempfile.TemporaryDirectory(prefix="inbox2action-stage10-tests-") as temp_dir:
                result = subprocess.run(
                    [sys.executable, "-m", "pytest", "-q", "--basetemp", temp_dir],
                    cwd=PROJECT_ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            summary = result.stdout + "\n" + result.stderr
            passed_match = re.search(r"(\d+) passed", summary)
            skipped_match = re.search(r"(\d+) skipped", summary)
            test_evidence = {
                "status": "PASS" if result.returncode == 0 else "FAIL",
                "returncode": result.returncode,
                "passed": int(passed_match.group(1)) if passed_match else 0,
                "skipped": int(skipped_match.group(1)) if skipped_match else 0,
                "stage8_excluded": False,
                "expected_live_skips_allowed": True,
            }
        report = run_stage10_report(
            args.dataset_root,
            mode=_mode(args),
            postgres_evidence=postgres_evidence,
            test_evidence=test_evidence,
            observed_evidence=observed_evidence,
        )
        _write_report(
            args.json_output,
            json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        )
        _write_report(args.markdown_output, render_stage10_markdown(report))
    except (OSError, ValueError, TypeError) as exc:
        print(f"stage10_evaluation_failed: {type(exc).__name__}: {exc}")
        return 1

    dataset = report["dataset"]
    if not isinstance(dataset, dict):
        dataset = {}
    print(
        json.dumps(
            {
                "stage": "stage10",
                "mode": report["mode"],
                "dataset_case_count": dataset.get("dataset_case_count", 0),
                "approved_cases": dataset.get("approved_cases", 0),
                "dataset_version": report["dataset_version"],
                "final_verdict": report["final_verdict"],
                "hard_gate_violations": report["hard_gate_violations"],
                "json_output": str(args.json_output),
                "markdown_output": str(args.markdown_output),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    verdict = report["final_verdict"]
    if verdict in {"PASS", "COMPLETE"}:
        return 0
    if verdict == "INCOMPLETE" or dataset.get("status") == "NEEDS_REVIEW":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
