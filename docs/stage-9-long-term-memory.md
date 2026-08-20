# Stage 9: Long-term User Preference Memory

Stage 9 extends the existing LangGraph workflow with four bounded preference
categories:

- `triage_preferences`
- `reply_preferences`
- `task_preferences`
- `calendar_preferences`

The owner is the normalized trusted Gmail account identity. The Store namespace
is `(account_id, category)`, and the backend is the existing
`AsyncPostgresStore`; no second memory database or business Alembic migration is
introduced. `AsyncPostgresStore.setup()` remains part of the existing Stage 4
runtime initialization.

## Write boundary

The existing `ApprovalInterrupt` edit/clarify path creates a typed
`UserEditDiff`. The diff records safe `before`, `after`, changed field names,
thread/action identity, and the approval revision. It never stores a raw reply
body, MIME, attachment, provider client, credential, or database session.

The evidence identity is a SHA-256 digest of the category, workflow/action
identity, approval revision, and normalized diff. Evidence is stored under a
deterministic key. A replay returns `ALREADY_APPLIED`; a material edit advances
the category's independent `version`; a no-op leaves the version unchanged.

The mutable category snapshot is a validated `MemoryDocument` with an
independent `schema_version`, `version`, evidence count, typed preference
payload, and timestamp. Store reads validate category-specific fields before
they become a `PreferenceContext`.

## Read boundary

Planners may call `plan_with_memory()` before the current model decision. The
planner receives only a bounded `PreferenceContext` serialized under
`LONG_TERM_SOFT_PREFERENCES`. It is explicitly a low-priority hint. Current
email instructions, security policy, tool permissions, trusted runtime
configuration, approval, and real observations take precedence.

In particular:

- Memory cannot choose `CLICKUP_LIST_ID` or any provider target.
- Memory cannot replace the canonical `Asia/Shanghai` business timezone.
- Calendar preference windows are ranked only after BUSY observations are
  removed.
- An explicit current task priority remains unchanged even when a default is
  remembered.

## Verification

Offline contracts cover namespaces, typed diffs, reply feature reduction,
no-op/duplicate/version behavior, account isolation, malicious state rejection,
precedence, the four-category Memory ON/OFF comparison, and existing HITL graph
integration. PostgreSQL validation uses the existing Stage 4 runtime and
reopens the Store before loading a new-thread preference.

For an explicit two-process validation against a dedicated test owner, run:

```powershell
uv run --frozen python scripts/run_stage9_memory_restart_validation.py --mode both --owner stage9-live-memory@example.test
```

The runner prints only bounded status/category/version/evidence metadata. It
does not call Gmail, DeepSeek, ClickUp, or Google Calendar.

Before calling the stage complete, run from the Stage 9 worktree:

```powershell
C:\pythonProject\Inbox2Action\.venv\Scripts\python.exe -m alembic current
C:\pythonProject\Inbox2Action\.venv\Scripts\python.exe -m alembic heads
C:\pythonProject\Inbox2Action\.venv\Scripts\python.exe -m pytest -q --basetemp .pytest-tmp
C:\pythonProject\Inbox2Action\.venv\Scripts\python.exe -m ruff check .
C:\pythonProject\Inbox2Action\.venv\Scripts\python.exe -m mypy src
git diff --check
```

PostgreSQL tests are opt-in and require `RUN_POSTGRES_INTEGRATION_TESTS=true`
plus the external `INBOX2ACTION_DATABASE_URL`. Live Gmail, model, ClickUp, and
Google Calendar calls remain separate from deterministic offline evidence.
