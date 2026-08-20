from __future__ import annotations

import os

import pytest

from inbox2action.memory import MemoryCategory, MemoryService, UserEditDiff
from inbox2action.stage4 import open_langgraph_postgres, upgrade_database

pytestmark = pytest.mark.integration


def _database_url() -> str:
    if os.getenv("RUN_POSTGRES_INTEGRATION_TESTS", "").lower() != "true":
        pytest.skip("set RUN_POSTGRES_INTEGRATION_TESTS=true for PostgreSQL tests")
    database_url = os.getenv("INBOX2ACTION_DATABASE_URL")
    if not database_url:
        pytest.fail("INBOX2ACTION_DATABASE_URL is required when PostgreSQL tests run")
    return database_url


@pytest.mark.asyncio
async def test_postgres_store_memory_survives_runtime_reopen_and_new_thread() -> None:
    database_url = _database_url()
    upgrade_database(database_url)
    owner = "stage9-memory@example.test"
    diff = UserEditDiff(
        category=MemoryCategory.TASK,
        thread_id="email:0123456789abcdef01234567",
        action_id="task-1",
        approval_revision=2,
        before={"priority": "medium"},
        after={"priority": "high"},
        preference_updates={"default_priority": "high"},
    )

    async with open_langgraph_postgres(database_url) as runtime:
        service = MemoryService(runtime.store)
        outcome, document = await service.apply_user_edit(owner, diff)
        assert outcome.value in {"APPLIED", "ALREADY_APPLIED"}
        assert document.typed_preferences().default_priority == "high"

    # A new runtime/store object is the process-restart boundary for this test.
    async with open_langgraph_postgres(database_url) as restarted:
        loaded = await MemoryService(restarted.store).load_context(owner)

    assert loaded.versions[MemoryCategory.TASK] >= 1
    assert loaded.task.default_priority == "high"
