"""Seed a writable Compose OAuth-token volume, then run an existing script."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from runpy import run_path


def _seed_token() -> None:
    source = Path(
        os.environ.get(
            "INBOX2ACTION_GMAIL_TOKEN_SOURCE",
            "/run/inbox2action/gmail-token-source.json",
        )
    )
    target = Path(
        os.environ.get(
            "GMAIL_TOKEN_PATH",
            "/var/lib/inbox2action/gmail-token.json",
        )
    )
    if not source.is_file():
        raise SystemExit("configured Gmail token source is unavailable")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        shutil.copyfile(source, temporary)
        temporary.chmod(0o600)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("a target script is required")
    _seed_token()
    target_script, *target_args = sys.argv[1:]
    sys.argv = [target_script, *target_args]
    run_path(target_script, run_name="__main__")


if __name__ == "__main__":
    main()
