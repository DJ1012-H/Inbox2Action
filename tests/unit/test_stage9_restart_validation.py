from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

from run_stage9_memory_restart_validation import _child_args, _run_async


def test_windows_runner_uses_selector_loop_without_changing_async_result(
    monkeypatch,
) -> None:
    async def loop_kind() -> bool:
        return isinstance(asyncio.get_running_loop(), asyncio.SelectorEventLoop)

    monkeypatch.setattr(sys, "platform", "win32")
    assert _run_async(loop_kind()) is True


def test_restart_still_dispatches_two_distinct_process_modes() -> None:
    args = argparse.Namespace(
        owner="account@example.test",
        old_thread="email:0123456789abcdef01234567",
        new_thread="email:0123456789abcdef01234568",
    )
    write = _child_args(args, "write")
    read = _child_args(args, "read")

    assert write != read
    assert "write" in write
    assert "read" in read
    assert "email:0123456789abcdef01234567" in write
    assert "email:0123456789abcdef01234568" in read
