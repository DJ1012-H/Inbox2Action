from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_final_development_cli_refuses_without_confirmations() -> None:
    script = (
        Path(__file__).parents[2]
        / "scripts"
        / "run_stage2_development_final.py"
    )

    completed = subprocess.run(
        [sys.executable, str(script), "--run-id", "run-01"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "development_run_refused" in completed.stderr
    assert "API" not in completed.stdout
