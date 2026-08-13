# Stage 4 Persistence Checkpoint

## Scope

Stage 4 adds durable checkpoint semantics to the Stage 3 workflow:

- stable thread identity;
- persisted normalized state through one LangGraph checkpointer;
- restart/resume from a new process/store instance;
- optimistic state-version protection;
- unique account/message identity;
- preservation of approval revisions, ActionPlan progress, and execution
  outcomes.

The Stage 4 implementation provides a Docker PostgreSQL service, LangGraph
`AsyncPostgresSaver` as the only short-term workflow checkpoint source,
`AsyncPostgresStore` for separately scoped preferences, and an Alembic-managed
execution ledger. The execution ledger does not duplicate workflow state; it
only claims provider side effects before they occur.

## Boundary

Only the validated `WorkflowState` is persisted. Raw MIME/HTML, credentials,
authorization headers, complete provider payloads, and hidden model reasoning
are not columns. Corrupt or schema-incompatible state fails closed instead of
being silently repaired.

## Recovery contract

1. Load the checkpoint by stable thread_id.
2. Validate the complete state against the Pydantic contract.
3. Resume only from the stored state version.
4. Resume a real LangGraph interrupt with the same thread ID.
5. Claim the idempotency key before provider execution.
6. Block `executing`/`unknown` claims instead of replaying a possible side
   effect.

The local tests cover real interrupt/edit/approve/reject behavior, multi-action
dependency ordering, and crash-window claim decisions. The opt-in Docker test
additionally closes and reopens the PostgreSQL runtime between interrupt and
approval, then verifies the checkpointer, execution ledger, and preference
store. It passed on Windows with Docker PostgreSQL on 2026-08-12 and remains
skipped in ordinary no-service runs unless `RUN_POSTGRES_INTEGRATION_TESTS` is
enabled.

## Local Docker workflow

```powershell
docker compose up -d postgres
$env:INBOX2ACTION_DATABASE_URL = "postgresql://inbox2action:inbox2action_dev@localhost:5432/inbox2action"
.\.venv\Scripts\python.exe scripts/setup_stage4_postgres.py
$env:RUN_POSTGRES_INTEGRATION_TESTS = "true"
.\.venv\Scripts\python.exe -m pytest tests/integration/test_stage4_postgres.py -q
```
