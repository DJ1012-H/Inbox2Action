"""Run the approved Pilot v1 assets through the deterministic offline Fake Model."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from pathlib import Path

from inbox2action.evaluation.asset_bundle import (
    load_evaluation_asset_bundle,
    validate_evaluation_asset_bundle,
)
from inbox2action.evaluation.pilot_fake_model import ApprovedPilotFakeModel
from inbox2action.evaluation.runner_v1 import (
    PilotCaseRunResultV1,
    PilotEvaluationRunnerV1,
    PilotEvaluationRunV1,
    write_pilot_evaluation_run,
)

PROJECT_ROOT = Path(__file__).parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("evaluation"))
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional redacted result file; it must stay under evaluation/results.",
    )
    return parser.parse_args()


def run_approved_pilot_fake_model(evaluation_root: Path) -> tuple[ApprovedPilotFakeModel, PilotEvaluationRunV1]:
    """Exercise the full injected-model path without any network client."""

    bundle = load_evaluation_asset_bundle(evaluation_root)
    validate_evaluation_asset_bundle(bundle, require_approved_reviews=True)
    model = ApprovedPilotFakeModel()
    run = PilotEvaluationRunnerV1(
        bundle,
        model,
        require_approved_reviews=True,
        failure_mode="continue",
    ).run()
    return model, run


def redacted_summary(run: PilotEvaluationRunV1) -> dict[str, int | float]:
    """Return only aggregate evaluation facts; never output email or Tool payloads."""

    results = run.results
    return {
        "case_count": len(results),
        "accepted_count": _count(results, lambda result: result.acceptance_passed is True),
        "infrastructure_error_count": _count(
            results, lambda result: result.status == "infrastructure_error"
        ),
        "triage_accuracy": _rate(results, lambda result: result.triage_correct is True),
        "tool_selection_accuracy": _rate(
            results, lambda result: result.tool_selection_correct is True
        ),
        "tool_sequence_accuracy": _rate(
            results, lambda result: result.tool_sequence_correct is True
        ),
        "arguments_valid_rate": _rate(
            results, lambda result: result.arguments_valid is True
        ),
        "fixture_resolution_rate": _rate(
            results, lambda result: result.fixture_resolution_passed is True
        ),
        "safety_pass_rate": _rate(results, lambda result: result.safety_passed is True),
        "external_side_effects": _sum_metric(results, "external_side_effects"),
        "unknown_tool_executions": _sum_metric(results, "unknown_tool_executions"),
        "loop_exceeded_count": _count(results, lambda result: result.loop_exceeded is True),
    }


def main() -> int:
    args = parse_args()
    try:
        _, run = run_approved_pilot_fake_model(args.root)
        summary = redacted_summary(run)
        if args.output is not None:
            write_pilot_evaluation_run(run, args.output, project_root=PROJECT_ROOT)
    except (OSError, TypeError, ValueError, AssertionError) as exc:
        print(f"pilot_fake_model_failed: {type(exc).__name__}: {exc}")
        return 1
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if _is_success(summary) else 1


def _count(
    results: Sequence[PilotCaseRunResultV1], predicate: Callable[[PilotCaseRunResultV1], bool]
) -> int:
    return sum(predicate(result) for result in results)


def _rate(
    results: Sequence[PilotCaseRunResultV1], predicate: Callable[[PilotCaseRunResultV1], bool]
) -> float:
    return _count(results, predicate) / len(results) if results else 0.0


def _sum_metric(results: Sequence[PilotCaseRunResultV1], attribute: str) -> int:
    values = [getattr(result, attribute) for result in results]
    if any(value is None for value in values):
        return -1
    return sum(values)


def _is_success(summary: dict[str, int | float]) -> bool:
    return (
        summary["case_count"] == 15
        and summary["accepted_count"] == 15
        and summary["infrastructure_error_count"] == 0
        and summary["triage_accuracy"] == 1.0
        and summary["tool_selection_accuracy"] == 1.0
        and summary["tool_sequence_accuracy"] == 1.0
        and summary["arguments_valid_rate"] == 1.0
        and summary["fixture_resolution_rate"] == 1.0
        and summary["safety_pass_rate"] == 1.0
        and summary["external_side_effects"] == 0
        and summary["unknown_tool_executions"] == 0
        and summary["loop_exceeded_count"] == 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
