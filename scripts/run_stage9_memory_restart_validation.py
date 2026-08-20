"""Run the Stage 9 write/read proof in separate Python processes.

This script performs no Gmail, model, ClickUp, or Calendar calls. It requires
an explicitly configured PostgreSQL URL and is intentionally opt-in.
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from inbox2action.config import Settings
from inbox2action.memory import MemoryCategory, MemoryService, UserEditDiff
from inbox2action.stage4 import open_langgraph_postgres, upgrade_database


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prove Stage 9 memory survives a process restart and new thread."
    )
    parser.add_argument("--mode", choices=("both", "write", "read"), default="both")
    parser.add_argument("--owner", default="stage9-live-memory@example.test")
    parser.add_argument("--old-thread", default="email:0123456789abcdef01234567")
    parser.add_argument("--new-thread", default="email:0123456789abcdef01234568")
    return parser


async def _write(owner: str, old_thread: str) -> int:
    settings = Settings()
    database_url = settings.database_url_value
    if not database_url:
        raise SystemExit("INBOX2ACTION_DATABASE_URL must be configured")
    upgrade_database(database_url)
    diff = UserEditDiff(
        category=MemoryCategory.TASK,
        thread_id=old_thread,
        action_id="stage9-live-task",
        approval_revision=1,
        before={"priority": "medium"},
        after={"priority": "high"},
        preference_updates={"default_priority": "high"},
    )
    async with open_langgraph_postgres(database_url) as runtime:
        outcome, document = await MemoryService(runtime.store).apply_user_edit(owner, diff)
    print(
        f"write status={outcome.value} category={MemoryCategory.TASK.value} "
        f"version={document.version} evidence_id={diff.evidence_id}"
    )
    return 0


async def _read(owner: str, new_thread: str) -> int:
    del new_thread  # the new thread is intentionally not part of the namespace
    settings = Settings()
    database_url = settings.database_url_value
    if not database_url:
        raise SystemExit("INBOX2ACTION_DATABASE_URL must be configured")
    async with open_langgraph_postgres(database_url) as runtime:
        context = await MemoryService(runtime.store).load_context(owner)
    loaded = context.task.default_priority == "high"
    print(
        f"read loaded={str(loaded).lower()} category={MemoryCategory.TASK.value} "
        f"version={context.versions[MemoryCategory.TASK]}"
    )
    return 0 if loaded else 1


def _child_args(args: argparse.Namespace, mode: str) -> list[str]:
    script = str(Path(__file__).resolve())
    return [
        sys.executable,
        script,
        "--mode",
        mode,
        "--owner",
        args.owner,
        "--old-thread",
        args.old_thread,
        "--new-thread",
        args.new_thread,
    ]


def run(args: argparse.Namespace) -> int:
    if args.mode == "write":
        return asyncio.run(_write(args.owner, args.old_thread))
    if args.mode == "read":
        return asyncio.run(_read(args.owner, args.new_thread))
    subprocess.run(_child_args(args, "write"), check=True)
    subprocess.run(_child_args(args, "read"), check=True)
    print(
        f"restart process_restarted=true old_thread={args.old_thread} "
        f"new_thread={args.new_thread}"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
