"""Export deterministic stage-two v3 JSON Schema artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import BaseModel

from inbox2action.evaluation.policy_v3 import ActionPlanV3, CaseExecutionPolicyV3
from inbox2action.evaluation.report_v3 import FormalValidationDecisionV3
from inbox2action.evaluation.runner_v3 import PilotEvaluationRunV3
from inbox2action.evaluation.triage_v3 import TriageResultV3

PROJECT_ROOT = Path(__file__).parents[1]
DEFAULT_OUTPUT_DIRECTORY = PROJECT_ROOT / "evaluation" / "schemas-v3"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIRECTORY,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_directory = args.output_dir.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    exports: tuple[tuple[type[BaseModel], str], ...] = (
        (ActionPlanV3, "stage2-action-plan-v3.schema.json"),
        (CaseExecutionPolicyV3, "stage2-case-policy-v3.schema.json"),
        (TriageResultV3, "stage2-triage-v3.schema.json"),
        (PilotEvaluationRunV3, "stage2-run-v3.schema.json"),
        (FormalValidationDecisionV3, "stage2-formal-decision-v3.schema.json"),
    )
    for model, filename in exports:
        payload = model.model_json_schema()
        payload["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        destination = output_directory / filename
        destination.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
