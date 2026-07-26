"""Export deterministic JSON Schema artifacts for the Pilot evaluation assets."""

from __future__ import annotations

import json
from pathlib import Path

from inbox2action.evaluation.assets import (
    EvaluationCaseV1,
    ReviewRecordV1,
    ToolFixtureV1,
)

PROJECT_ROOT = Path(__file__).parents[1]
SCHEMA_DIRECTORY = PROJECT_ROOT / "evaluation" / "schemas"


def main() -> None:
    SCHEMA_DIRECTORY.mkdir(parents=True, exist_ok=True)
    for model, filename in (
        (EvaluationCaseV1, "evaluation-case.schema.json"),
        (ToolFixtureV1, "tool-fixture.schema.json"),
        (ReviewRecordV1, "review-record.schema.json"),
    ):
        destination = SCHEMA_DIRECTORY / filename
        payload = model.model_json_schema(by_alias=True)
        destination.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
