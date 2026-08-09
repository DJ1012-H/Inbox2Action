from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_stage2_v3_schema_export_is_versioned_and_complete(tmp_path: Path) -> None:
    script = Path(__file__).parents[2] / "scripts" / "export_stage2_v3_schemas.py"

    completed = subprocess.run(
        [sys.executable, str(script), "--output-dir", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    expected = {
        "stage2-action-plan-v3.schema.json",
        "stage2-case-policy-v3.schema.json",
        "stage2-triage-v3.schema.json",
        "stage2-run-v3.schema.json",
        "stage2-formal-decision-v3.schema.json",
    }
    assert {path.name for path in tmp_path.glob("*.json")} == expected
    for filename in expected:
        payload = json.loads((tmp_path / filename).read_text(encoding="utf-8"))
        assert payload["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert payload["title"]
