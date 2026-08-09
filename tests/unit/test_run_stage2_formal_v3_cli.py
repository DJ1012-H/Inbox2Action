from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_formal_v3_cli_refuses_without_all_explicit_live_confirmations() -> None:
    script = Path(__file__).parents[2] / "scripts" / "run_stage2_formal_v3.py"

    completed = subprocess.run(
        [sys.executable, str(script)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "formal_run_refused" in completed.stderr
    assert "API" not in completed.stdout
