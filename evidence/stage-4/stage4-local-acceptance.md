# Stage 4 Local and Docker Acceptance

Implementation date: 2026-08-09

Docker acceptance date: 2026-08-12

## Implemented

- Docker Compose service based on `postgres:17-alpine` with a health check and
  persistent named volume;
- LangGraph `AsyncPostgresSaver` as the only short-term workflow state source;
- `AsyncPostgresStore` for separately scoped preferences;
- Alembic-managed SQLAlchemy/Psycopg execution claim ledger;
- a claim-before-side-effect and start-before-call protocol that blocks replay
  after a crash window;
- one integration case covering runtime reconnect, interrupt resume, ledger
  execution, and preference recovery.

## Measured result

The complete no-service suite remains `263 passed, 3 skipped`; its PostgreSQL
case is intentionally opt-in. With Docker Desktop 4.85.0 and PostgreSQL
`17-alpine` running, Alembic upgraded the database through
`0002_execution_ledger` and the opt-in Stage 4 integration test completed as:

```text
1 passed in 2.81s
```

The case persisted a real LangGraph interrupt, closed the runtime, reopened it
with the same thread ID, approved and executed the pending action once, and
recovered the stored preference. Stage 4 therefore passes its Docker
PostgreSQL acceptance gate.

## Docker acceptance command

```powershell
docker compose up -d postgres
$env:INBOX2ACTION_DATABASE_URL = "postgresql://inbox2action:inbox2action_dev@localhost:5432/inbox2action"
$env:RUN_POSTGRES_INTEGRATION_TESTS = "true"
.\.venv\Scripts\python.exe -m pytest tests/integration/test_stage4_postgres.py -q
```

This command is the reproducible Stage 4 Docker acceptance check.
