from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from inbox2action.evaluation.runner_v1 import (
    PilotEvaluationRunV1,
    write_pilot_evaluation_run,
)

PROJECT_ROOT = Path(__file__).parents[2]
SCRIPT = PROJECT_ROOT / "scripts" / "run_pilot_evaluation.py"


def test_cli_allows_only_the_empty_dry_run_mode(tmp_path: Path) -> None:
    allowed = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path / "evaluation"), "--dry-run", "--allow-empty"],
        check=False, capture_output=True, text=True,
    )
    assert allowed.returncode == 0
    assert '"case_count": 0' in allowed.stdout

    live = subprocess.run([sys.executable, str(SCRIPT)], check=False, capture_output=True, text=True)
    assert live.returncode != 0
    assert "live model execution is not enabled" in live.stdout


def test_cli_rejects_output_outside_results(tmp_path: Path) -> None:
    command = [
        sys.executable, str(SCRIPT), "--root", str(tmp_path / "evaluation"),
        "--dry-run", "--allow-empty", "--output", str(tmp_path / "outside.json"),
    ]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    assert result.returncode != 0
    assert not (tmp_path / "outside.json").exists()


def test_result_writer_keeps_outputs_in_results_and_round_trips(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    destination = project_root / "evaluation" / "results" / "pilot.json"
    run = PilotEvaluationRunV1(mode="dry_run", results=[])
    write_pilot_evaluation_run(run, destination, project_root=project_root)
    loaded = PilotEvaluationRunV1.model_validate_json(destination.read_text(encoding="utf-8"))
    assert loaded == run
    with pytest.raises(ValueError):
        write_pilot_evaluation_run(run, tmp_path / "outside.json", project_root=project_root)
