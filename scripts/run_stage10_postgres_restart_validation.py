"""Validate Stage 10 PostgreSQL checkpoint recovery across two processes.

This is an opt-in evidence runner.  It reuses the existing Stage 3 graph,
Stage 4 PostgreSQL runtime, execution ledger, and fixture executor.  It never
calls a model or a real provider; the only external state it writes is the
explicitly configured local PostgreSQL test state.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import selectors
import subprocess
import sys
import tempfile
from collections.abc import Coroutine, Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

from langgraph.types import Command

from inbox2action.config import Settings
from inbox2action.evaluation.policy_v3 import (
    ActionNodeV3,
    ActionPlanV3,
    ParameterResolutionStatus,
    ParameterResolutionV3,
)
from inbox2action.evaluation.triage_v3 import TriageResultV3
from inbox2action.llm.models import TriageDecision
from inbox2action.stage3 import (
    ActionProposal,
    EmailEnvelope,
    FixtureWriteExecutor,
    Stage2PlanningBundle,
    build_email_action_graph,
    prepare_workflow_state,
    workflow_state_to_graph,
)
from inbox2action.stage4 import open_langgraph_postgres, upgrade_database


def _selector_loop() -> asyncio.AbstractEventLoop:
    return asyncio.SelectorEventLoop(selectors.SelectSelector())


def _run_async[T](coro: Coroutine[Any, Any, T]) -> T:
    if sys.platform == "win32":
        with asyncio.Runner(loop_factory=_selector_loop) as runner:
            return runner.run(coro)
    return asyncio.run(coro)


def _database_url() -> str:
    database_url = Settings().database_url_value
    if not database_url:
        raise SystemExit("INBOX2ACTION_DATABASE_URL must be configured")
    return database_url


def _prepared_state(message_id: str):
    triage = TriageResultV3(
        decision=TriageDecision.ACTION_REQUIRED,
        reason="Stage 10 cross-process checkpoint validation",
        confidence=1.0,
        suspected_prompt_injection=False,
        security_reason=None,
        safe_to_plan_actions=True,
    )
    action = ActionNodeV3(
        action_id="stage10-postgres-checkpoint",
        tool_name="save_reply_draft",
        required_parameters=("subject", "body"),
        parameter_resolutions=(
            ParameterResolutionV3(
                field_name="subject",
                status=ParameterResolutionStatus.RESOLVED,
                source="stage10_validation",
            ),
            ParameterResolutionV3(
                field_name="body",
                status=ParameterResolutionStatus.RESOLVED,
                source="stage10_validation",
            ),
        ),
        requires_approval=True,
    )
    proposal = ActionProposal(
        action_id=action.action_id,
        tool_name=action.tool_name,
        parameters={
            "recipient": "stage10@example.test",
            "subject": "Stage 10 checkpoint",
            "body": "Persist this fixture proposal across process restart.",
        },
    )
    return prepare_workflow_state(
        EmailEnvelope(
            account_id="stage10-postgres-validation",
            message_id=message_id,
            from_address="stage10@example.test",
            subject="Stage 10 checkpoint",
            body="Persist this fixture proposal across process restart.",
        ),
        Stage2PlanningBundle(
            triage=triage,
            action_plan=ActionPlanV3(actions=(action,)),
            proposals=[proposal],
        ),
    )


async def _write(message_id: str) -> dict[str, object]:
    database_url = _database_url()
    upgrade_database(database_url)
    state = _prepared_state(message_id)
    config = {"configurable": {"thread_id": state.thread_id}}
    async with open_langgraph_postgres(database_url) as runtime:
        graph = build_email_action_graph(
            checkpointer=runtime.checkpointer,
            store=runtime.store,
            execution_ledger=runtime.execution_ledger,
            write_executor=FixtureWriteExecutor(),
        )
        result = await graph.ainvoke(workflow_state_to_graph(state), config)
    interrupt = result.get("__interrupt__")
    if not interrupt or interrupt[0].value.get("revision") != 1:
        raise RuntimeError("checkpoint write did not persist approval revision 1")
    return {
        "phase": "write",
        "thread_id": state.thread_id,
        "approval_revision": interrupt[0].value["revision"],
        "status": "waiting_for_approval",
    }


async def _resume(message_id: str) -> dict[str, object]:
    database_url = _database_url()
    state = _prepared_state(message_id)
    config = {"configurable": {"thread_id": state.thread_id}}
    executor = FixtureWriteExecutor()
    async with open_langgraph_postgres(database_url) as runtime:
        graph = build_email_action_graph(
            checkpointer=runtime.checkpointer,
            store=runtime.store,
            execution_ledger=runtime.execution_ledger,
            write_executor=executor,
        )
        result = await graph.ainvoke(
            Command(resume={"decision": "approve", "expected_revision": 1}),
            config,
        )
    if result.get("status") != "completed":
        raise RuntimeError(f"checkpoint resume did not complete: {result.get('status')}")
    if len(executor.calls) != 1:
        raise RuntimeError(f"fixture executor calls={len(executor.calls)}, expected 1")
    return {
        "phase": "resume",
        "thread_id": state.thread_id,
        "status": "completed",
        "fixture_provider_write_count": len(executor.calls),
    }


def _child_args(mode: str, message_id: str) -> list[str]:
    return [
        sys.executable,
        str(Path(__file__).resolve()),
        "--mode",
        mode,
        "--message-id",
        message_id,
    ]


def _run_postgres_integration_suite(database_url: str) -> dict[str, object]:
    project_root = Path(__file__).resolve().parents[1]
    test_paths = [
        "tests/integration/test_stage4_postgres.py",
        "tests/integration/test_stage6_postgres.py",
        "tests/integration/test_stage7_postgres.py",
        "tests/integration/test_stage8_postgres.py",
        "tests/integration/test_stage9_postgres.py",
    ]
    environment = os.environ.copy()
    environment["RUN_POSTGRES_INTEGRATION_TESTS"] = "true"
    environment["INBOX2ACTION_DATABASE_URL"] = database_url
    with tempfile.TemporaryDirectory(prefix="inbox2action-stage10-pg-") as temp_dir:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                *test_paths,
                "--basetemp",
                temp_dir,
            ],
            cwd=project_root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
    summary = result.stdout + "\n" + result.stderr
    passed_match = re.search(r"(\d+) passed", summary)
    skipped_match = re.search(r"(\d+) skipped", summary)
    passed = int(passed_match.group(1)) if passed_match else 0
    skipped = int(skipped_match.group(1)) if skipped_match else 0
    if result.returncode != 0 or passed != len(test_paths):
        raise RuntimeError(
            "PostgreSQL integration failed: "
            f"returncode={result.returncode} passed={passed} skipped={skipped}"
        )
    return {
        "status": "PASS",
        "tests": len(test_paths),
        "passed": passed,
        "skipped": skipped,
        "checkpoint_persistence": "PASS",
        "execution_ledger_persistence": "PASS",
        "memory_persistence": "PASS",
        "account_isolation": "PASS",
    }


def _run_memory_restart_validation() -> dict[str, object]:
    project_root = Path(__file__).resolve().parents[1]
    script = project_root / "scripts" / "run_stage9_memory_restart_validation.py"
    owner = f"stage10-memory-{uuid4()}@example.test"
    old_thread = "email:" + "c" * 24
    new_thread = "email:" + "d" * 24
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--mode",
            "both",
            "--owner",
            owner,
            "--old-thread",
            old_thread,
            "--new-thread",
            new_thread,
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    output = result.stdout + "\n" + result.stderr
    if result.returncode != 0 or "read loaded=true" not in output or "process_restarted=true" not in output:
        raise RuntimeError("Stage 9 cross-process memory validation failed")
    return {
        "status": "PASS",
        "memory_restart": "PASS",
        "process_restarted": True,
    }


def _run_both(message_id: str) -> dict[str, object]:
    database_url = _database_url()
    integration = _run_postgres_integration_suite(database_url)
    write = subprocess.run(
        _child_args("write", message_id),
        check=True,
        capture_output=True,
        text=True,
    )
    resume = subprocess.run(
        _child_args("resume", message_id),
        check=True,
        capture_output=True,
        text=True,
    )
    write_result = json.loads(write.stdout.strip())
    resume_result = json.loads(resume.stdout.strip())
    if write_result["phase"] != "write" or resume_result["phase"] != "resume":
        raise RuntimeError("unexpected child phase result")
    memory = _run_memory_restart_validation()
    return {
        "status": "PASS",
        "checkpoint_restart": "PASS",
        "memory_restart": memory["memory_restart"],
        "postgresql_integration": integration,
        "process_a": write_result,
        "process_b": resume_result,
        "fixture_provider_write_count": resume_result["fixture_provider_write_count"],
        "real_provider_writes": 0,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("both", "write", "resume"), default="both")
    parser.add_argument("--message-id", default=f"stage10-{uuid4()}")
    parser.add_argument("--json-output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.mode == "write":
        result = _run_async(_write(args.message_id))
    elif args.mode == "resume":
        result = _run_async(_resume(args.message_id))
    else:
        result = _run_both(args.message_id)
    rendered = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.json_output is not None:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
